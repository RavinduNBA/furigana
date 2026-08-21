"""Deterministic learner-assistance selection over approved analysis records."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
PRESET_SCHEMA_VERSION = 1
PROFILE_SCHEMA_VERSION = 1
EXPOSURE_SCHEMA_VERSION = 1

READING_STATES = {"show-reading", "hide-reading"}
MEANING_STATES = {"show-meaning", "hide-meaning"}
GRAMMAR_STATES = {"show-grammar", "hide-grammar"}
DIMENSIONS = {"reading", "meaning", "grammar"}
ITEM_KINDS = {"vocabulary", "expression", "name", "grammar"}
PRECEDENCE = [
    "publisher",
    "explicit_user_override",
    "preset",
    "exposure_policy",
    "frequency_or_familiarity_evidence",
    "dictionary",
    "model",
]
HEX_SHA256 = re.compile(r"[0-9a-f]{64}")
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
UNSAFE_TEXT = re.compile(
    r"[<>\x00-\x08\x0b\x0c\x0e-\x1f]|https?://|(?:^|\s)[A-Za-z]:\\|"
    r"(?:^|\s)/(?:home|etc|var|tmp)/|(?:api[_-]?key|password|token)\s*=",
    re.IGNORECASE,
)


class LearnerProfileError(ValueError):
    """Raised when learner-assistance inputs cannot be trusted."""


def stable_hash(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def serialize_assistance_report(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise LearnerProfileError("Expected a JSON object")
    return value


def _without_hash(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != "hash"}


def add_hash(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    result["hash"] = stable_hash(result)
    return result


def _check_hash(value: dict[str, Any], label: str) -> None:
    if value.get("hash") != stable_hash(_without_hash(value)):
        raise LearnerProfileError(f"Invalid {label} hash")


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise LearnerProfileError(f"Invalid {label} ID")
    return value


def _safe_text(value: Any, label: str, *, maximum: int = 160) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or UNSAFE_TEXT.search(value)
    ):
        raise LearnerProfileError(f"Unsafe {label}")
    return value


def _ids(values: list[dict[str, Any]], label: str) -> list[str]:
    result = [_safe_id(value.get("id"), label) for value in values]
    if len(result) != len(set(result)):
        raise LearnerProfileError(f"Duplicate {label} ID")
    return result


def _valid_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _validate_exact_fields(value: dict[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise LearnerProfileError(f"Unsupported {label} fields")


def _state_for_dimension(dimension: str) -> set[str]:
    return {
        "reading": READING_STATES,
        "meaning": MEANING_STATES,
        "grammar": GRAMMAR_STATES,
    }[dimension]


def validate_preset_dataset(dataset: dict[str, Any]) -> None:
    _validate_exact_fields(
        dataset,
        {
            "schema_version",
            "dataset_id",
            "dataset_version",
            "fixture_notice",
            "source_provenance",
            "presets",
            "hash",
        },
        "preset dataset",
    )
    if dataset["schema_version"] != PRESET_SCHEMA_VERSION:
        raise LearnerProfileError("Unsupported preset schema")
    _safe_id(dataset["dataset_id"], "preset dataset")
    _safe_text(dataset["dataset_version"], "preset dataset version")
    _safe_text(dataset["fixture_notice"], "preset fixture notice")
    _safe_text(dataset["source_provenance"], "preset provenance")
    presets = dataset["presets"]
    if not isinstance(presets, list) or len(presets) != 3:
        raise LearnerProfileError("Preset dataset requires N5, N4, and N3")
    if _ids(presets, "preset") != ["phase8-preset-n5", "phase8-preset-n4", "phase8-preset-n3"]:
        raise LearnerProfileError("Unstable preset ordering")
    for preset, level in zip(presets, ("N5", "N4", "N3")):
        _validate_exact_fields(
            preset,
            {
                "id",
                "schema_version",
                "level",
                "reading_default",
                "meaning_default",
                "grammar_default",
                "frequency_thresholds",
                "exposure_thresholds",
                "rationale_codes",
                "source_provenance",
                "hash",
            },
            "preset",
        )
        if preset["schema_version"] != PRESET_SCHEMA_VERSION or preset["level"] != level:
            raise LearnerProfileError("Invalid preset identity")
        if preset["reading_default"] not in READING_STATES:
            raise LearnerProfileError("Invalid preset reading state")
        if preset["meaning_default"] not in MEANING_STATES:
            raise LearnerProfileError("Invalid preset meaning state")
        if preset["grammar_default"] not in GRAMMAR_STATES:
            raise LearnerProfileError("Invalid preset grammar state")
        for key in ("reading_rank", "meaning_rank", "grammar_rank"):
            if not isinstance(preset["frequency_thresholds"].get(key), int):
                raise LearnerProfileError("Invalid preset frequency threshold")
        if set(preset["frequency_thresholds"]) != {"reading_rank", "meaning_rank", "grammar_rank"}:
            raise LearnerProfileError("Unsupported preset frequency thresholds")
        if set(preset["exposure_thresholds"]) != DIMENSIONS:
            raise LearnerProfileError("Unsupported preset exposure thresholds")
        if any(not isinstance(value, int) or value < 1 for value in preset["exposure_thresholds"].values()):
            raise LearnerProfileError("Invalid preset exposure threshold")
        if not isinstance(preset["rationale_codes"], list) or any(
            not isinstance(value, str) or not SAFE_ID.fullmatch(value)
            for value in preset["rationale_codes"]
        ):
            raise LearnerProfileError("Invalid preset rationale")
        _safe_text(preset["source_provenance"], "preset provenance")
        _check_hash(preset, "preset")
    # Assistance must decrease monotonically from N5 to N3.
    def assistance(preset):
        return sum(
            state.startswith("show-")
            for state in (
                preset["reading_default"],
                preset["meaning_default"],
                preset["grammar_default"],
            )
        )
    if [assistance(value) for value in presets] != [3, 2, 0]:
        raise LearnerProfileError("Preset assistance ordering is not N5, N4, N3")
    _check_hash(dataset, "preset dataset")


def validate_profile(
    profile: dict[str, Any],
    preset_dataset: dict[str, Any],
    source_hashes: dict[str, str],
) -> None:
    _validate_exact_fields(
        profile,
        {
            "schema_version",
            "id",
            "label",
            "preset_id",
            "reading_assistance_policy",
            "meaning_assistance_policy",
            "grammar_assistance_policy",
            "overrides",
            "exposure_policy",
            "source_references",
            "provenance",
            "hash",
        },
        "profile",
    )
    if profile["schema_version"] != PROFILE_SCHEMA_VERSION:
        raise LearnerProfileError("Unsupported profile schema")
    _safe_id(profile["id"], "profile")
    _safe_text(profile["label"], "profile label")
    if profile["provenance"] not in {"local-synthetic-fixture", "user"}:
        raise LearnerProfileError("Invalid profile provenance")
    presets = {value["id"]: value for value in preset_dataset["presets"]}
    if profile["preset_id"] is not None and profile["preset_id"] not in presets:
        raise LearnerProfileError("Unknown preset")
    policies = {
        "reading": profile["reading_assistance_policy"],
        "meaning": profile["meaning_assistance_policy"],
        "grammar": profile["grammar_assistance_policy"],
    }
    for dimension, policy in policies.items():
        if policy.get("state") == "suppress-publisher-ruby":
            raise LearnerProfileError("Publisher-ruby suppression attempt")
        if set(policy) != {"state"} or policy["state"] not in _state_for_dimension(dimension) | {"preset"}:
            raise LearnerProfileError(f"Invalid {dimension} state")
        if policy["state"] == "preset" and profile["preset_id"] is None:
            raise LearnerProfileError("Preset policy has no preset")
    if set(profile["exposure_policy"]) != {"enabled", "dimensions"}:
        raise LearnerProfileError("Invalid exposure policy")
    if not isinstance(profile["exposure_policy"]["enabled"], bool):
        raise LearnerProfileError("Invalid exposure policy")
    dimensions = profile["exposure_policy"]["dimensions"]
    if not isinstance(dimensions, list) or len(dimensions) != len(set(dimensions)) or any(
        value not in DIMENSIONS for value in dimensions
    ):
        raise LearnerProfileError("Invalid exposure dimensions")
    expected_refs = {
        "vocabulary_hash": source_hashes["vocabulary"],
        "annotation_plan_hash": source_hashes["annotation_plan"],
        "grammar_plan_hash": source_hashes["grammar_plan"],
        "preset_dataset_hash": preset_dataset["hash"],
    }
    if profile["source_references"] != expected_refs:
        raise LearnerProfileError("Source-hash mismatch")

    overrides = profile["overrides"]
    if not isinstance(overrides, list):
        raise LearnerProfileError("Invalid overrides")
    override_ids = _ids(overrides, "override")
    if override_ids != sorted(override_ids):
        raise LearnerProfileError("Unordered overrides")
    seen_targets: set[tuple[str, str]] = set()
    for override in overrides:
        _validate_exact_fields(
            override,
            {
                "id",
                "target_id",
                "target_kind",
                "dimension",
                "state",
                "reviewer_note",
                "reviewer",
                "review_date",
                "provenance",
                "hash",
            },
            "override",
        )
        _safe_id(override["target_id"], "override target")
        if override["target_kind"] not in ITEM_KINDS:
            raise LearnerProfileError("Invalid override target kind")
        dimension = override["dimension"]
        if dimension not in DIMENSIONS or override["state"] not in _state_for_dimension(dimension):
            raise LearnerProfileError("Invalid override state")
        if (dimension == "grammar") != (override["target_kind"] == "grammar"):
            raise LearnerProfileError("Cross-kind override")
        if override["reviewer_note"] is not None:
            _safe_text(override["reviewer_note"], "override note")
        _safe_text(override["reviewer"], "override reviewer", maximum=80)
        if not _valid_date(override["review_date"]) or override["provenance"] != "user":
            raise LearnerProfileError("Invalid reviewer/date/provenance")
        key = (override["target_id"], dimension)
        if key in seen_targets:
            raise LearnerProfileError("Duplicate override")
        seen_targets.add(key)
        _check_hash(override, "override")
    _check_hash(profile, "profile")


def validate_exposure_history(
    history: dict[str, Any] | None,
    source_hashes: dict[str, str],
) -> None:
    if history is None:
        return
    _validate_exact_fields(
        history,
        {
            "schema_version",
            "id",
            "book_id",
            "source_references",
            "provenance",
            "records",
            "hash",
        },
        "exposure history",
    )
    if history["schema_version"] != EXPOSURE_SCHEMA_VERSION:
        raise LearnerProfileError("Unsupported exposure schema")
    _safe_id(history["id"], "exposure history")
    if history["source_references"] != {
        "annotation_plan_hash": source_hashes["annotation_plan"],
        "grammar_plan_hash": source_hashes["grammar_plan"],
    }:
        raise LearnerProfileError("Source-hash mismatch")
    if history["provenance"] != "explicit-local-history":
        raise LearnerProfileError("Invalid exposure provenance")
    records = history["records"]
    if not isinstance(records, list):
        raise LearnerProfileError("Invalid exposure records")
    exposure_ids = _ids(records, "exposure")
    if exposure_ids != sorted(exposure_ids):
        raise LearnerProfileError("Unordered exposures")
    seen: set[tuple[str, str]] = set()
    for record in records:
        _validate_exact_fields(
            record,
            {
                "id",
                "target_id",
                "target_kind",
                "dimension",
                "count",
                "occurrence_ids",
                "last_observed",
                "provenance",
                "hash",
            },
            "exposure",
        )
        _safe_id(record["target_id"], "exposure target")
        if record["target_kind"] not in ITEM_KINDS:
            raise LearnerProfileError("Invalid exposure target kind")
        dimension = record["dimension"]
        if dimension not in DIMENSIONS or (dimension == "grammar") != (record["target_kind"] == "grammar"):
            raise LearnerProfileError("Exposure dimension mismatch")
        if not isinstance(record["count"], int) or record["count"] < 0:
            raise LearnerProfileError("Negative exposure count")
        if not isinstance(record["occurrence_ids"], list) or len(record["occurrence_ids"]) != len(set(record["occurrence_ids"])):
            raise LearnerProfileError("Invalid exposure occurrences")
        if record["last_observed"] is not None and set(record["last_observed"]) != {
            "chapter_id", "sentence_id", "occurrence_id"
        }:
            raise LearnerProfileError("Invalid last-observed location")
        if record["provenance"] != "explicit-local-history":
            raise LearnerProfileError("Invalid exposure provenance")
        key = (record["target_id"], dimension)
        if key in seen:
            raise LearnerProfileError("Duplicate exposure")
        seen.add(key)
        _check_hash(record, "exposure")
    _check_hash(history, "exposure history")


def _validate_sources(
    vocabulary: dict[str, Any],
    annotation_plan: dict[str, Any],
    grammar_plan: dict[str, Any] | None,
) -> tuple[dict[str, str], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    if vocabulary.get("schema_version") != 4:
        raise LearnerProfileError("Unsupported vocabulary schema")
    if annotation_plan.get("schema_version") != 2:
        raise LearnerProfileError("Unsupported annotation-plan schema")
    book_id = vocabulary.get("book_id")
    if not isinstance(book_id, str) or annotation_plan.get("book_id") != book_id:
        raise LearnerProfileError("Source book mismatch")
    if grammar_plan is not None and (
        grammar_plan.get("schema_version") != 1
        or grammar_plan.get("book_id") != book_id
        or not grammar_plan.get("config", {}).get("enabled")
    ):
        raise LearnerProfileError("Invalid grammar plan")
    source_hashes = {
        "vocabulary": stable_hash(vocabulary),
        "annotation_plan": stable_hash(annotation_plan),
        "grammar_plan": stable_hash(grammar_plan) if grammar_plan is not None else "none",
    }
    items: dict[str, dict[str, Any]] = {}
    occurrences: dict[str, dict[str, Any]] = {}
    for item in annotation_plan.get("items", []):
        item_id = _safe_id(item.get("id"), "study item")
        if item_id in items or item.get("kind") not in ITEM_KINDS - {"grammar"}:
            raise LearnerProfileError("Duplicate or unsupported study item")
        item_occurrences = item.get("occurrences")
        if not isinstance(item_occurrences, list) or not item_occurrences:
            raise LearnerProfileError("Study item has no occurrences")
        for occurrence in item_occurrences:
            occurrence_id = _safe_id(occurrence.get("id"), "study occurrence")
            if occurrence_id in occurrences:
                raise LearnerProfileError("Duplicate study occurrence")
            occurrences[occurrence_id] = occurrence
        items[item_id] = item
    grammar_items: dict[str, dict[str, Any]] = {}
    if grammar_plan is not None:
        grammar_occurrences = grammar_plan.get("occurrences", [])
        for occurrence in grammar_occurrences:
            occurrence_id = _safe_id(occurrence.get("id"), "grammar occurrence")
            if occurrence_id in occurrences:
                raise LearnerProfileError("Duplicate grammar occurrence")
            _check_hash(occurrence, "grammar occurrence")
            occurrences[occurrence_id] = occurrence
        for item in grammar_plan.get("items", []):
            item_id = _safe_id(item.get("id"), "grammar item")
            if item_id in items or item_id in grammar_items:
                raise LearnerProfileError("Duplicate grammar item")
            if item.get("selection_status") != "selected":
                raise LearnerProfileError("Unsupported grammar selection status")
            if any(value not in occurrences for value in item.get("occurrence_ids", [])):
                raise LearnerProfileError("Unknown grammar occurrence")
            _check_hash(item, "grammar item")
            grammar_items[item_id] = item
    return source_hashes, items, grammar_items


def _preset_state(preset: dict[str, Any], dimension: str) -> str:
    return preset[f"{dimension}_default"]


def _hidden_state(dimension: str) -> str:
    return {"reading": "hide-reading", "meaning": "hide-meaning", "grammar": "hide-grammar"}[dimension]


def _select_dimension(
    *,
    dimension: str,
    profile: dict[str, Any],
    preset: dict[str, Any] | None,
    override: dict[str, Any] | None,
    exposure: dict[str, Any] | None,
) -> tuple[str, str, list[str]]:
    policy = profile[f"{dimension}_assistance_policy"]["state"]
    if policy == "preset":
        if preset is None:
            raise LearnerProfileError("Unknown preset")
        state = _preset_state(preset, dimension)
        source = "preset"
        rationale = [f"preset-{preset['level'].lower()}-{dimension}-default"]
    else:
        state = policy
        source = "profile"
        rationale = [f"profile-{dimension}-default"]
    if (
        exposure is not None
        and profile["exposure_policy"]["enabled"]
        and dimension in profile["exposure_policy"]["dimensions"]
    ):
        if preset is None:
            raise LearnerProfileError("Exposure policy requires a preset")
        threshold = preset["exposure_thresholds"][dimension]
        if exposure["count"] >= threshold:
            state = _hidden_state(dimension)
            source = "exposure_policy"
            rationale = [f"exposure-{dimension}-threshold-met", f"preset-{preset['level'].lower()}-threshold-{threshold}"]
        else:
            rationale.append(f"exposure-{dimension}-below-threshold")
    if override is not None:
        state = override["state"]
        source = "explicit_user_override"
        rationale = [f"explicit-user-{dimension}-override"]
    return state, source, rationale


def _diagnostic(reason: str, source_id: str = "assistance-selection") -> dict[str, Any]:
    value = {
        "id": "assistance-diagnostic-0001",
        "reason": reason,
        "source_id": source_id,
    }
    return add_hash(value)


def _empty_report(book_id: str | None, reason: str) -> dict[str, Any]:
    value = {
        "schema_version": SCHEMA_VERSION,
        "report_id": "assistance-selection-report-v1",
        "book_id": book_id,
        "source_schema_versions": {
            "vocabulary": 4,
            "annotation_plan": 2,
            "grammar_plan": 1,
            "profile": PROFILE_SCHEMA_VERSION,
            "preset_dataset": PRESET_SCHEMA_VERSION,
            "exposure_history": EXPOSURE_SCHEMA_VERSION,
        },
        "source_hashes": {},
        "precedence": PRECEDENCE,
        "preset_dataset": None,
        "profile": None,
        "configuration": {"enabled": False, "exposure_enabled": False, "hash": stable_hash({"enabled": False, "exposure_enabled": False})},
        "results": [],
        "diagnostics": [_diagnostic(reason)],
    }
    value["hash"] = stable_hash(value)
    return value


def build_assistance_report(
    vocabulary: dict[str, Any],
    annotation_plan: dict[str, Any],
    grammar_plan: dict[str, Any] | None,
    profile: dict[str, Any] | None,
    preset_dataset: dict[str, Any] | None,
    exposure_history: dict[str, Any] | None = None,
    *,
    enabled: bool = False,
) -> dict[str, Any]:
    if not enabled:
        return _empty_report(annotation_plan.get("book_id"), "disabled")
    source_hashes, study_items, grammar_items = _validate_sources(
        vocabulary, annotation_plan, grammar_plan
    )
    if profile is None or preset_dataset is None:
        raise LearnerProfileError("Missing profile or preset dataset")
    validate_preset_dataset(preset_dataset)
    validate_profile(profile, preset_dataset, source_hashes)
    validate_exposure_history(exposure_history, source_hashes)
    if exposure_history is not None and exposure_history["book_id"] != annotation_plan["book_id"]:
        raise LearnerProfileError("Source book mismatch")

    all_items = {**study_items, **grammar_items}
    occurrence_ids = {
        item_id: [value["id"] for value in item.get("occurrences", [])]
        if item_id in study_items
        else list(item.get("occurrence_ids", []))
        for item_id, item in all_items.items()
    }
    occurrence_locations = {
        value["id"]: value
        for item in study_items.values()
        for value in item.get("occurrences", [])
    }
    if grammar_plan is not None:
        occurrence_locations.update(
            {value["id"]: value for value in grammar_plan.get("occurrences", [])}
        )
    overrides: dict[tuple[str, str], dict[str, Any]] = {}
    for override in profile["overrides"]:
        item = all_items.get(override["target_id"])
        if item is None:
            raise LearnerProfileError("Unknown override")
        actual_kind = "grammar" if override["target_id"] in grammar_items else item["kind"]
        if override["target_kind"] != actual_kind:
            raise LearnerProfileError("Cross-kind override")
        overrides[(override["target_id"], override["dimension"])] = override

    exposures: dict[tuple[str, str], dict[str, Any]] = {}
    if exposure_history is not None:
        for exposure in exposure_history["records"]:
            item = all_items.get(exposure["target_id"])
            if item is None:
                raise LearnerProfileError("Unknown exposure target")
            actual_kind = "grammar" if exposure["target_id"] in grammar_items else item["kind"]
            if exposure["target_kind"] != actual_kind:
                raise LearnerProfileError("Exposure dimension mismatch")
            expected_occurrences = occurrence_ids[exposure["target_id"]]
            if any(value not in expected_occurrences for value in exposure["occurrence_ids"]):
                raise LearnerProfileError("Unknown occurrence reference")
            selected_occurrences = set(exposure["occurrence_ids"])
            if exposure["occurrence_ids"] != [
                value for value in expected_occurrences if value in selected_occurrences
            ]:
                raise LearnerProfileError("Unordered exposure occurrences")
            if exposure["last_observed"] is not None:
                observed = exposure["last_observed"]
                source = occurrence_locations.get(observed["occurrence_id"])
                if (
                    observed["occurrence_id"] not in expected_occurrences
                    or source is None
                    or observed["chapter_id"] != source.get("chapter_id")
                    or observed["sentence_id"] != source.get("sentence_id")
                ):
                    raise LearnerProfileError("Unknown occurrence reference")
            exposures[(exposure["target_id"], exposure["dimension"])] = exposure

    preset = next(
        (value for value in preset_dataset["presets"] if value["id"] == profile["preset_id"]),
        None,
    )
    results = []
    ordered = [(item_id, item, item["kind"]) for item_id, item in study_items.items()]
    ordered += [(item_id, item, "grammar") for item_id, item in grammar_items.items()]
    for item_id, item, kind in ordered:
        applicable_dimensions = ("grammar",) if kind == "grammar" else ("reading", "meaning")
        states = {"reading": None, "meaning": None, "grammar": None}
        sources = {"reading": None, "meaning": None, "grammar": None}
        rationales: list[str] = []
        applicable_override_ids = []
        applicable_exposure_ids = []
        for dimension in applicable_dimensions:
            override = overrides.get((item_id, dimension))
            exposure = exposures.get((item_id, dimension))
            state, source, reasons = _select_dimension(
                dimension=dimension,
                profile=profile,
                preset=preset,
                override=override,
                exposure=exposure,
            )
            states[dimension] = state
            sources[dimension] = source
            rationales.extend(reasons)
            if override:
                applicable_override_ids.append(override["id"])
            if exposure:
                applicable_exposure_ids.append(exposure["id"])
        protected = False
        if kind == "grammar":
            grammar_occurrences = {
                value["id"]: value for value in grammar_plan.get("occurrences", [])
            }
            protected = any(
                grammar_occurrences[value].get("publisher_ruby_interaction")
                != "none"
                for value in item["occurrence_ids"]
            )
            authoritative_reading = None
            reading_source = None
            approved_meaning_reference = None
        else:
            protected = bool(item.get("publisher_ruby_id")) or any(
                value.get("publisher_ruby_id") for value in item.get("occurrences", [])
            )
            authoritative_reading = item.get("reading")
            reading_source = item.get("reading_source")
            approved_meaning_reference = {
                "item_id": item_id,
                "selected_entry_id": item.get("selected_entry_id"),
                "selected_sense_id": item.get("selected_sense_id"),
                "selected_translation_id": item.get("selected_translation_id"),
            }
        if protected:
            rationales.append("publisher-ruby-preserved")
        result = {
            "id": f"assistance-result-{len(results) + 1:04d}",
            "source_item_id": item_id,
            "item_kind": kind,
            "occurrence_ids": occurrence_ids[item_id],
            "authoritative_reading": authoritative_reading,
            "reading_source": reading_source,
            "approved_meaning_reference": approved_meaning_reference,
            "preset_id": profile["preset_id"],
            "exposure_ids": applicable_exposure_ids,
            "override_ids": applicable_override_ids,
            "reading_assistance": states["reading"],
            "meaning_assistance": states["meaning"],
            "grammar_assistance": states["grammar"],
            "effective_sources": sources,
            "rationale_codes": rationales,
            "publisher_ruby_protection": "preserved-authoritative" if protected else "not-applicable",
        }
        results.append(add_hash(result))

    configuration = {
        "enabled": True,
        "exposure_enabled": profile["exposure_policy"]["enabled"] and exposure_history is not None,
    }
    configuration["hash"] = stable_hash(configuration)
    value = {
        "schema_version": SCHEMA_VERSION,
        "report_id": "assistance-selection-report-v1",
        "book_id": annotation_plan["book_id"],
        "source_schema_versions": {
            "vocabulary": 4,
            "annotation_plan": 2,
            "grammar_plan": 1 if grammar_plan is not None else None,
            "profile": PROFILE_SCHEMA_VERSION,
            "preset_dataset": PRESET_SCHEMA_VERSION,
            "exposure_history": EXPOSURE_SCHEMA_VERSION if exposure_history is not None else None,
        },
        "source_hashes": {
            **source_hashes,
            "profile": profile["hash"],
            "preset_dataset": preset_dataset["hash"],
            "exposure_history": exposure_history["hash"] if exposure_history else "none",
        },
        "precedence": PRECEDENCE,
        "preset_dataset": {
            "id": preset_dataset["dataset_id"],
            "version": preset_dataset["dataset_version"],
            "hash": preset_dataset["hash"],
        },
        "profile": {"id": profile["id"], "hash": profile["hash"]},
        "configuration": configuration,
        "results": results,
        "diagnostics": [],
    }
    value["hash"] = stable_hash(value)
    return value


def safe_build_assistance_report(
    vocabulary: dict[str, Any],
    annotation_plan: dict[str, Any],
    grammar_plan: dict[str, Any] | None,
    profile: dict[str, Any] | None,
    preset_dataset: dict[str, Any] | None,
    exposure_history: dict[str, Any] | None = None,
    *,
    enabled: bool = False,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    if not enabled:
        return _empty_report(annotation_plan.get("book_id"), "disabled")
    if failure_reason:
        return _empty_report(annotation_plan.get("book_id"), failure_reason)
    try:
        return build_assistance_report(
            vocabulary,
            annotation_plan,
            grammar_plan,
            profile,
            preset_dataset,
            exposure_history,
            enabled=True,
        )
    except LearnerProfileError as error:
        message = str(error).lower()
        reasons = (
            ("unknown preset", "unknown-preset"),
            ("duplicate override", "duplicate-override"),
            ("unknown override", "unknown-override"),
            ("cross-kind override", "cross-kind-override"),
            ("negative exposure", "negative-exposure-count"),
            ("duplicate exposure", "duplicate-exposure"),
            ("unknown occurrence", "unknown-occurrence-reference"),
            ("dimension mismatch", "dimension-mismatch"),
            ("source-hash mismatch", "source-hash-mismatch"),
            ("publisher-ruby", "publisher-ruby-suppression-attempt"),
            ("unsafe", "invalid-input"),
        )
        reason = next((code for text, code in reasons if text in message), "invalid-input")
        return _empty_report(annotation_plan.get("book_id"), reason)


def validate_assistance_report(
    vocabulary: dict[str, Any],
    annotation_plan: dict[str, Any],
    grammar_plan: dict[str, Any] | None,
    profile: dict[str, Any],
    preset_dataset: dict[str, Any],
    exposure_history: dict[str, Any] | None,
    report: dict[str, Any],
) -> None:
    expected = build_assistance_report(
        vocabulary,
        annotation_plan,
        grammar_plan,
        profile,
        preset_dataset,
        exposure_history,
        enabled=True,
    )
    if report != expected:
        raise LearnerProfileError("Assistance report is not deterministic or valid")
