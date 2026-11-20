"""Put the parts together from the configuration: secrets, API clients, records,
spend, answerer, rollover, group watcher, dispatcher, the voting page and the web app.

Called by the entry point.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path

import anthropic
import httpx2
from fastapi import APIRouter, FastAPI

from line_group_agent.agent.answerer import Answerer
from line_group_agent.agent.client_tools import ClientTools
from line_group_agent.agent.message_deleter import MessageDeleter
from line_group_agent.agent.model_caller import ModelCaller
from line_group_agent.agent.prompt import build_system
from line_group_agent.agent.rollover import Rollover
from line_group_agent.agent.summary_scrubber import SummaryScrubber
from line_group_agent.alerts.alert_notifier import AlertNotifier
from line_group_agent.bills.bill_tools import bill_tools
from line_group_agent.cards.card_image_finder import CardImageFinder
from line_group_agent.config.agent_config import AgentConfig, ConfigError, load_secrets
from line_group_agent.config.settings_store import SettingsStore
from line_group_agent.events.event_dispatcher import EventDispatcher, NoticeTexts
from line_group_agent.events.group_watcher import GroupWatcher
from line_group_agent.events.mention_limiter import MentionLimiter
from line_group_agent.events.postback_handler import PostbackHandler
from line_group_agent.events.wait_notice import WaitNotice
from line_group_agent.itinerary.itinerary_book import ItineraryBook
from line_group_agent.itinerary.itinerary_replier import ItineraryReplier
from line_group_agent.itinerary.itinerary_tools import itinerary_tools
from line_group_agent.liff.liff_itineraries import LiffItineraries
from line_group_agent.liff.liff_members import LiffMembers
from line_group_agent.liff.liff_page import load_itinerary_page, load_liff_page
from line_group_agent.liff.liff_polls import LiffPolls
from line_group_agent.liff.liff_router import build_liff_router
from line_group_agent.liff.request_limiter import RequestLimiter
from line_group_agent.liff.verify_failure_limiter import VerifyFailureLimiter
from line_group_agent.line_api.line_client import LineClient
from line_group_agent.line_api.login_client import LoginClient
from line_group_agent.line_api.push_quota import PushQuota
from line_group_agent.media.image_store import ImageStore
from line_group_agent.media.media_recorder import MediaRecorder
from line_group_agent.media.photo_picker import PhotoPicker
from line_group_agent.polls.poll_book import PollBook
from line_group_agent.polls.poll_tools import poll_tools
from line_group_agent.records.group_conversations import GroupConversations
from line_group_agent.records.group_log import GroupLog
from line_group_agent.records.retention_sweeper import RetentionSweeper
from line_group_agent.records.summary_journal import SummaryJournal
from line_group_agent.reminders.push_left import PushLeft
from line_group_agent.reminders.reminder_book import ReminderBook
from line_group_agent.reminders.reminder_sender import ROUND_INTERVAL_SECONDS, ReminderSender
from line_group_agent.reminders.reminder_tools import reminder_tools
from line_group_agent.service.patrol import Patrol
from line_group_agent.spend.spend_books import SpendBooks
from line_group_agent.spend.spend_ledger import SpendLedger
from line_group_agent.stickers.sticker_tools import sticker_tools
from line_group_agent.tabs.tabs_file import TabsFile
from line_group_agent.webhook.webhook_app import create_app

ANTHROPIC_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_TIMEOUT_SECONDS = 300.0


def build_app(config: AgentConfig, clock: Callable[[], datetime] | None = None) -> FastAPI:
    """Read the secrets and the persona, open the records, and return the web app. `clock`
    is the bot's time (the simulator moves it); without one it is the machine's."""
    secrets = load_secrets(config)
    try:
        persona = config.persona_file.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigError(f"cannot read persona_file: {error.strerror}") from error

    clock = clock or _machine_time
    intro = _read_intro(config)
    settings = SettingsStore(config.settings_file)
    group_log = GroupLog(config.state_dir)
    journal = SummaryJournal(config.state_dir)
    conversations = GroupConversations(config.state_dir, group_log, journal)
    conversations.open(config.allowed_group_ids)
    overall = SpendLedger(config.state_dir / "spend.json", config.budget)
    overall.open()
    books = SpendBooks(overall, config.state_dir, config.budget, settings, conversations.count)
    tabs = TabsFile(config.tabs_file, conversations, books, settings, clock)

    client = create_anthropic_client(secrets.anthropic_api_key)
    line = LineClient(
        secrets.line_channel_access_token,
        base_url=config.line_api_base_url,
        data_base_url=config.line_data_api_base_url,
    )
    notifier = AlertNotifier(line, config.alert_user_id or config.required_member_user_id)
    polls = PollBook(config.state_dir, clock)
    itineraries = ItineraryBook(config.state_dir, clock)
    push_quota = PushQuota(line)
    push_left = PushLeft(push_quota)
    reminders = ReminderBook(config.state_dir, clock)
    reminder_sender = ReminderSender(reminders, line, push_left, clock)
    client_tools = ClientTools(
        [
            *poll_tools(polls, liff_id=config.liff_id),
            *itinerary_tools(itineraries, liff_id=config.liff_id, clock=clock),
            *bill_tools(),
            *reminder_tools(
                reminders,
                push_left,
                max_per_month=config.max_reminders_per_group_per_month,
                min_push_left=config.wait_min_push_left,
                clock=clock,
            ),
            *sticker_tools(config.stickers),
        ]
    )
    caller = ModelCaller(
        config,
        client,
        build_system(persona),
        books,
        observer=notifier,
        extra_tools=client_tools.definitions(),
    )
    scrubber = SummaryScrubber(config, caller, journal, conversations, books)
    deleter = MessageDeleter(
        group_log, conversations, search_limit=config.history_search_limit, scrubber=scrubber
    )
    images = ImageStore(config.state_dir)
    card_images = CardImageFinder() if config.card_image_lookup else None
    answerer = Answerer(
        config,
        caller,
        group_log,
        conversations,
        books,
        deleter,
        client_tools=client_tools,
        photos=PhotoPicker(images, config.max_images_per_turn),
        card_images=card_images,
    )
    rollover = Rollover(config, caller, journal, books, settings, clock)
    retention = RetentionSweeper(conversations, group_log, config.retention_days, clock)
    watcher = GroupWatcher(
        conversations,
        tabs,
        line,
        rollover,
        settings,
        clock,
        retention=retention,
        scrubber=scrubber,
    )
    tabs.refresh()
    dispatcher = EventDispatcher(
        config.allowed_group_ids,
        line,
        group_log,
        answerer,
        redelivered_answer_window_seconds=config.redelivered_answer_window_seconds,
        required_member_user_id=config.required_member_user_id,
        call_names=config.call_names,
        call_name_anywhere=config.call_name_anywhere,
        call_name_start_runs_on=config.call_name_start_runs_on,
        allow_groups_with_required_member=config.allow_groups_with_required_member,
        observer=watcher,
        texts=NoticeTexts(
            error=config.error_text,
            rate_limit=config.rate_limit_text,
            intro=intro,
            welcome=config.welcome_text,
            help=_read_text_file(config.help_file, "help_file"),
            help_keywords=config.help_keywords,
            itinerary_keywords=config.itinerary_keywords,
        ),
        limiter=MentionLimiter(config.max_mentions_per_user_per_hour),
        wait_notice=WaitNotice(
            line,
            push_quota,
            config.wait_text,
            min_push_left=config.wait_min_push_left,
        ),
        deleter=deleter,
        postbacks=PostbackHandler(polls),
        itineraries=ItineraryReplier(itineraries, liff_id=config.liff_id, clock=clock),
        media=_media_recorder(config, line, images),
        notifier=notifier,
    )
    closers = [line.close, client.close]
    if card_images is not None:
        closers.append(card_images.close)
    routers = _liff_routers(config, polls, itineraries, line, clock, closers)
    app = create_app(
        secrets.line_channel_secret,
        config.max_body_bytes,
        dispatcher,
        on_close=closers,
        background=[
            Patrol(watcher.patrol, config.patrol_interval_seconds),
            Patrol(reminder_sender.send_due, ROUND_INTERVAL_SECONDS),
        ],
        routers=routers,
    )
    # Read-only handle for a runner that must know when every queued event is handled.
    app.state.event_sink = dispatcher
    # A runner that moves the clock runs a reminder round itself, without waiting a minute.
    app.state.run_reminder_round = reminder_sender.send_due
    return app


def _machine_time() -> datetime:
    return datetime.now().astimezone()


def _liff_routers(
    config: AgentConfig,
    polls: PollBook,
    itineraries: ItineraryBook,
    line: LineClient,
    clock: Callable[[], datetime],
    closers: list[Callable[[], Awaitable[None]]],
) -> list[APIRouter]:
    """Return the routes of the voting page and the itinerary page, or none when `liff_id` is
    not set (the pages and their API then do not exist). The Login client it opens is added to
    `closers`."""
    if config.liff_id is None or config.login_channel_id is None:
        return []
    login = LoginClient(base_url=config.line_api_base_url)
    closers.append(login.close)
    members = LiffMembers(line)
    limiter = RequestLimiter(config.liff_max_requests_per_user_per_minute)
    verify_failures = VerifyFailureLimiter(
        config.liff_max_failed_verifies_per_minute,
        config.liff_max_failed_verifies_per_source_per_minute,
    )

    def is_group_allowed(group_id: str) -> bool:
        return group_id in config.allowed_group_ids or config.allow_groups_with_required_member

    service = LiffPolls(
        polls,
        login,
        members,
        limiter,
        verify_failures,
        login_channel_id=config.login_channel_id,
        is_group_allowed=is_group_allowed,
        clock=clock,
    )
    itinerary_service = LiffItineraries(
        itineraries,
        service.gate,
        members,
        is_group_allowed=is_group_allowed,
    )
    return [
        build_liff_router(
            load_liff_page(config.liff_id),
            service,
            max_body_bytes=config.liff_max_body_bytes,
            itinerary_page=load_itinerary_page(config.liff_id),
            itineraries=itinerary_service,
        )
    ]


def _media_recorder(
    config: AgentConfig, line: LineClient, images: ImageStore
) -> MediaRecorder | None:
    """Return the recorder of photos, or None when `max_images_per_turn` is 0 (photos are
    then neither kept nor recorded)."""
    if config.max_images_per_turn == 0:
        return None
    return MediaRecorder(line, images, config.max_image_edge_pixels)


def _read_intro(config: AgentConfig) -> str:
    if config.intro_file is None:
        return ""
    try:
        return config.intro_file.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise ConfigError(f"cannot read intro_file: {error.strerror}") from error


def create_anthropic_client(api_key: str) -> anthropic.AsyncAnthropic:
    """Return an API client that takes nothing from environment variables.

    The key, the address and tracing are given explicitly, and the HTTP client is a
    plain one with `trust_env=False`: the SDK's default HTTP client adds proxies from
    the environment even when told not to trust it.
    """
    http_client = httpx2.AsyncClient(timeout=ANTHROPIC_TIMEOUT_SECONDS, trust_env=False)
    return anthropic.AsyncAnthropic(
        api_key=api_key,
        base_url=ANTHROPIC_BASE_URL,
        open_telemetry=False,
        http_client=http_client,
    )


def _read_text_file(path: Path | None, key: str) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise ConfigError(f"cannot read {key}: {error.strerror}") from error
