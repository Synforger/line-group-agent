import json
from pathlib import Path

import pytest

from line_group_agent.config.agent_config import (
    ConfigError,
    load_config,
    load_secrets,
    parse_config,
)
from line_group_agent.stickers.default_stickers import DEFAULT_STICKERS
from line_group_agent.stickers.sticker import Sticker
from tests.fakes import make_config, raw_config


def test_defaults_match_the_agreed_receiving_point(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.host == "127.0.0.1"
    assert config.port == 8790
    assert config.max_body_bytes == 1024 * 1024
    assert config.model == "claude-haiku-5-5"
    assert config.max_tokens == 1024
    assert config.recent_message_count == 30
    assert config.max_tool_rounds == 4
    assert config.history_search_limit == 20
    assert config.redelivered_answer_window_seconds == 600
    assert config.required_member_user_id is None
    assert config.allow_groups_with_required_member is False
    assert config.help_file is None
    assert config.help_keywords == ("help",)
    assert config.call_names == ()
    assert config.call_name_anywhere is False
    assert config.call_name_start_runs_on is False
    assert config.card_image_lookup is True
    assert config.web_search is not None and config.web_search.max_uses == 3
    assert config.budget.currency == "JPY"
    assert config.budget.exhausted_text == "This month's budget is used up."
    assert config.budget.shared_spend_files == ()
    assert config.allowed_group_ids == frozenset({"Callowed"})


def test_every_default_can_be_set(tmp_path: Path) -> None:
    config = make_config(
        tmp_path, host="0.0.0.0", port=9000, max_body_bytes=10, recent_message_count=5
    )
    assert (config.host, config.port, config.max_body_bytes) == ("0.0.0.0", 9000, 10)
    assert config.recent_message_count == 5


def test_a_web_tool_set_to_null_is_off(tmp_path: Path) -> None:
    config = make_config(tmp_path, web_fetch=None)
    assert config.web_fetch is None


@pytest.mark.parametrize("key", ["persona_file", "state_dir", "prices_usd", "budget"])
def test_required_settings_are_required(tmp_path: Path, key: str) -> None:
    raw = raw_config(tmp_path)
    del raw[key]
    with pytest.raises(ConfigError, match=key):
        parse_config(raw, tmp_path)


def test_prices_have_no_default(tmp_path: Path) -> None:
    raw = raw_config(tmp_path)
    del raw["prices_usd"]["output_per_mtok"]
    with pytest.raises(ConfigError, match="output_per_mtok"):
        parse_config(raw, tmp_path)


def test_an_old_tab_name_setting_is_accepted_and_ignored(tmp_path: Path) -> None:
    config = make_config(tmp_path, tab_name="group-trip")
    assert not hasattr(config, "tab_name")


def test_the_settings_and_tab_files_default_to_the_config_folder_and_the_state_folder(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    assert config.settings_file == tmp_path / "settings.json"
    assert config.tabs_file == tmp_path / "state" / "tabs.json"


def test_the_settings_and_tab_files_can_be_named(tmp_path: Path) -> None:
    config = make_config(tmp_path, settings_file="ui/s.json", tabs_file="/abs/tabs.json")
    assert config.settings_file == tmp_path / "ui" / "s.json"
    assert config.tabs_file == Path("/abs/tabs.json")


def test_the_conversation_settings_have_defaults(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.cache_ttl == "1h"
    assert config.max_catch_up_messages == 200
    assert config.summary_max_tokens == 2048
    assert config.patrol_interval_seconds == 600


def test_the_cache_ttl_is_five_minutes_or_one_hour(tmp_path: Path) -> None:
    assert make_config(tmp_path, cache_ttl="5m").cache_ttl == "5m"
    with pytest.raises(ConfigError, match="cache_ttl"):
        make_config(tmp_path, cache_ttl="2h")


def test_names_are_read_anywhere_only_when_asked_for(tmp_path: Path) -> None:
    assert make_config(tmp_path, call_name_anywhere=True).call_name_anywhere is True
    with pytest.raises(ConfigError, match="call_name_anywhere"):
        make_config(tmp_path, call_name_anywhere="yes")


def test_a_glued_name_at_the_start_calls_only_when_asked_for(tmp_path: Path) -> None:
    assert make_config(tmp_path, call_name_start_runs_on=True).call_name_start_runs_on is True
    with pytest.raises(ConfigError, match="call_name_start_runs_on"):
        make_config(tmp_path, call_name_start_runs_on="yes")


def test_the_card_picture_lookup_is_on_unless_turned_off(tmp_path: Path) -> None:
    assert make_config(tmp_path, card_image_lookup=False).card_image_lookup is False
    assert make_config(tmp_path, card_image_lookup=True).card_image_lookup is True
    with pytest.raises(ConfigError, match="card_image_lookup"):
        make_config(tmp_path, card_image_lookup="yes")


def test_the_stickers_default_to_the_built_in_list_and_can_be_listed_or_turned_off(
    tmp_path: Path,
) -> None:
    assert make_config(tmp_path).stickers == DEFAULT_STICKERS
    assert make_config(tmp_path, stickers={}).stickers == ()
    config = make_config(
        tmp_path,
        stickers={"ありがとう": {"package_id": "8515", "sticker_id": 16581243}},
    )
    assert config.stickers == (Sticker("ありがとう", "8515", "16581243"),)


@pytest.mark.parametrize(
    "stickers",
    [
        {"": {"package_id": "1", "sticker_id": "2"}},
        {"x" * 21: {"package_id": "1", "sticker_id": "2"}},
        {"a": {"package_id": "1"}},
        {"a": {"package_id": "one", "sticker_id": "2"}},
        {"a": {"package_id": True, "sticker_id": "2"}},
        {"a": "1/2"},
        {"a ": {"package_id": "1", "sticker_id": "2"}, "a": {"package_id": "1", "sticker_id": "3"}},
        {str(n): {"package_id": "1", "sticker_id": "2"} for n in range(51)},
        ["a"],
    ],
)
def test_a_bad_sticker_list_is_refused(tmp_path: Path, stickers: object) -> None:
    with pytest.raises(ConfigError, match="sticker"):
        make_config(tmp_path, stickers=stickers)


def test_a_wrong_kind_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="port"):
        make_config(tmp_path, port="8790")
    with pytest.raises(ConfigError, match="port"):
        make_config(tmp_path, port=True)


def test_load_config_reads_a_file(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw_config(tmp_path)))
    assert load_config(path).state_dir == tmp_path / "state"


def test_load_config_names_a_broken_file(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{")
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(path)


def test_secrets_are_read_from_their_files(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.anthropic_api_key_file.write_text("key-value\n")
    config.line_channel_secret_file.write_text("secret-value")
    config.line_channel_access_token_file.write_text("token-value")
    secrets = load_secrets(config)
    assert secrets.anthropic_api_key == "key-value"
    assert secrets.line_channel_secret == "secret-value"
    assert secrets.line_channel_access_token == "token-value"


def test_an_empty_secret_file_is_refused_without_showing_content(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.anthropic_api_key_file.write_text("key-value")
    config.line_channel_secret_file.write_text("  \n")
    config.line_channel_access_token_file.write_text("token-value")
    with pytest.raises(ConfigError) as error:
        load_secrets(config)
    assert "line_channel_secret_file" in str(error.value)
    assert "key-value" not in str(error.value)


def test_relative_paths_are_taken_from_the_config_files_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "conf"
    folder.mkdir()
    raw = raw_config(tmp_path, persona_file="persona.md", state_dir="../state")
    raw["anthropic_api_key_file"] = "/absolute/key"
    (folder / "config.json").write_text(json.dumps(raw))
    monkeypatch.chdir(tmp_path)
    config = load_config(Path("conf/config.json"))
    assert config.persona_file == folder.resolve() / "persona.md"
    assert config.state_dir == folder.resolve() / "../state"
    assert config.anthropic_api_key_file == Path("/absolute/key")


def test_a_tilde_is_not_expanded_from_the_environment(tmp_path: Path) -> None:
    config = make_config(tmp_path, persona_file="~/persona.md")
    assert config.persona_file == tmp_path / "~" / "persona.md"


def test_the_v03_settings_have_their_defaults(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.alert_user_id is None and config.intro_file is None
    assert config.error_text and config.wait_text and config.rate_limit_text
    assert config.wait_min_push_left == 20
    assert config.max_mentions_per_user_per_hour == 20
    assert config.retention_days == 30


def test_the_v03_settings_can_be_set_and_the_intro_path_is_read_from_the_config_folder(
    tmp_path: Path,
) -> None:
    config = make_config(
        tmp_path,
        alert_user_id="Uop",
        intro_file="intro.txt",
        error_text="E",
        wait_text="W",
        wait_min_push_left=0,
        max_mentions_per_user_per_hour=5,
        rate_limit_text="R",
        retention_days=7,
    )
    assert config.alert_user_id == "Uop" and config.intro_file == tmp_path / "intro.txt"
    assert (config.error_text, config.wait_text, config.rate_limit_text) == ("E", "W", "R")
    assert config.wait_min_push_left == 0
    assert config.max_mentions_per_user_per_hour == 5 and config.retention_days == 7


@pytest.mark.parametrize(
    "key", ["max_mentions_per_user_per_hour", "retention_days", "wait_min_push_left"]
)
def test_the_counts_cannot_be_below_their_minimum(tmp_path: Path, key: str) -> None:
    with pytest.raises(ConfigError, match=key):
        make_config(tmp_path, **{key: -1})
    with pytest.raises(ConfigError, match=key):
        make_config(tmp_path, **{key: "many"})
    if key != "wait_min_push_left":
        with pytest.raises(ConfigError, match=key):
            make_config(tmp_path, **{key: 0})


def test_the_monthly_reminder_count_defaults_to_ten_and_can_be_set_down_to_zero(
    tmp_path: Path,
) -> None:
    assert make_config(tmp_path).max_reminders_per_group_per_month == 10
    config = make_config(tmp_path, max_reminders_per_group_per_month=0)
    assert config.max_reminders_per_group_per_month == 0
    with pytest.raises(ConfigError, match="max_reminders_per_group_per_month"):
        make_config(tmp_path, max_reminders_per_group_per_month=-1)
    with pytest.raises(ConfigError, match="max_reminders_per_group_per_month"):
        make_config(tmp_path, max_reminders_per_group_per_month="ten")


def test_the_itinerary_keywords_default_to_one_word_and_can_be_listed(tmp_path: Path) -> None:
    assert make_config(tmp_path).itinerary_keywords == ("itinerary",)
    config = make_config(tmp_path, itinerary_keywords=[" しおり ", "plan"])
    assert config.itinerary_keywords == ("しおり", "plan")


def test_an_itinerary_keyword_must_be_a_non_empty_string(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="itinerary_keywords"):
        make_config(tmp_path, itinerary_keywords=["ok", ""])


def test_the_photo_settings_have_defaults_and_limits(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert (config.max_images_per_turn, config.max_image_edge_pixels) == (3, 1568)
    config = make_config(tmp_path, max_images_per_turn=0, max_image_edge_pixels=64)
    assert (config.max_images_per_turn, config.max_image_edge_pixels) == (0, 64)


@pytest.mark.parametrize("overrides", [{"max_images_per_turn": -1}, {"max_image_edge_pixels": 63}])
def test_photo_settings_below_their_minimum_are_refused(
    tmp_path: Path, overrides: dict[str, int]
) -> None:
    with pytest.raises(ConfigError, match="at least"):
        make_config(tmp_path, **overrides)


def test_the_public_address_is_unset_by_default_and_loses_a_trailing_slash(tmp_path: Path) -> None:
    assert make_config(tmp_path).public_base_url is None
    config = make_config(tmp_path, public_base_url="https://bot.example.com/")
    assert config.public_base_url == "https://bot.example.com"


def test_a_public_address_that_is_not_http_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="public_base_url"):
        make_config(tmp_path, public_base_url="bot.example.com")


def test_the_welcome_text_is_empty_by_default_and_trimmed(tmp_path: Path) -> None:
    assert make_config(tmp_path).welcome_text == ""
    assert make_config(tmp_path, welcome_text="  Welcome!\n").welcome_text == "Welcome!"


def test_the_voting_page_is_off_unless_both_ids_are_given(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.liff_id is None and config.login_channel_id is None
    assert config.liff_max_requests_per_user_per_minute == 60
    assert config.liff_max_body_bytes == 1024
    assert config.liff_max_failed_verifies_per_minute == 30
    assert config.liff_max_failed_verifies_per_source_per_minute == 10


def test_the_voting_page_settings_can_be_set(tmp_path: Path) -> None:
    config = make_config(
        tmp_path,
        liff_id="1234567890-AbCdEfGh",
        login_channel_id="1234567890",
        liff_max_requests_per_user_per_minute=10,
        liff_max_body_bytes=512,
        liff_max_failed_verifies_per_minute=5,
        liff_max_failed_verifies_per_source_per_minute=2,
    )
    assert config.liff_id == "1234567890-AbCdEfGh"
    assert config.login_channel_id == "1234567890"
    assert config.liff_max_requests_per_user_per_minute == 10
    assert config.liff_max_body_bytes == 512
    assert config.liff_max_failed_verifies_per_minute == 5
    assert config.liff_max_failed_verifies_per_source_per_minute == 2


@pytest.mark.parametrize(
    "given",
    [{"liff_id": "1234567890-AbCdEfGh"}, {"login_channel_id": "1234567890"}],
)
def test_one_of_the_two_ids_alone_is_refused(tmp_path: Path, given: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match="together"):
        make_config(tmp_path, **given)


@pytest.mark.parametrize("bad", ["", "a b", "1234/5", "1234?p=1", "x" * 65, "<script>"])
def test_an_id_that_does_not_fit_in_an_address_is_refused(tmp_path: Path, bad: str) -> None:
    with pytest.raises(ConfigError, match="liff_id"):
        make_config(tmp_path, liff_id=bad, login_channel_id="1234567890")


@pytest.mark.parametrize(
    "key",
    [
        "liff_max_requests_per_user_per_minute",
        "liff_max_body_bytes",
        "liff_max_failed_verifies_per_minute",
        "liff_max_failed_verifies_per_source_per_minute",
    ],
)
def test_the_limits_must_be_positive(tmp_path: Path, key: str) -> None:
    with pytest.raises(ConfigError, match=key):
        make_config(tmp_path, **{key: 0})


def test_the_example_configuration_names_the_voting_page_with_made_up_values() -> None:
    raw = json.loads((Path(__file__).parents[2] / "configs" / "config.example.json").read_text())
    assert raw["liff_id"] == "1234567890-AbCdEfGh" and raw["login_channel_id"] == "1234567890"


def test_shared_spend_files_are_read_from_the_configuration_folder(tmp_path: Path) -> None:
    budget = {
        "monthly_limit": 1000,
        "currency_per_usd": 150,
        "shared_spend_files": ["other/spend.json", str(tmp_path / "absolute.json")],
    }
    config = make_config(tmp_path, budget=budget)
    assert config.budget.shared_spend_files == (
        tmp_path / "other" / "spend.json",
        tmp_path / "absolute.json",
    )


def test_shared_spend_files_must_be_a_list_of_names(tmp_path: Path) -> None:
    budget = {"monthly_limit": 1000, "currency_per_usd": 150, "shared_spend_files": [1]}
    with pytest.raises(ConfigError):
        make_config(tmp_path, budget=budget)
