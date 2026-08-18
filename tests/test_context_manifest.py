import copy
import json
import subprocess
from pathlib import Path

import pytest

from furiganalyse.book_context import serialize
from furiganalyse.context_manifest import (
    ContextManifestError, build_augmentation, build_manifest, disabled_context,
    export_registries, rehash_manifest, validate_edited_manifest,
)

ROOT=Path(__file__).resolve().parents[1]
def load(path): return json.loads((ROOT/path).read_text(encoding="utf-8"))

@pytest.fixture
def sources():
    return [load(path) for path in (
        "artifacts/phase6/run-a/context-index.json",
        "artifacts/phase6/evidence/run-a/evidence.json",
        "artifacts/phase6/terminology/run-a/consistency.json",
        "artifacts/phase6/summaries/run-a/packets.json",
        "artifacts/phase6/summaries/run-a/summary.json",
    )]

@pytest.fixture
def manifest(sources): return build_manifest(*sources)
@pytest.fixture
def edited(): return load("tests/fixtures/phase6-edited-context-manifest-v1.json")

def test_manifest_is_deterministic_and_matches_golden(sources,manifest):
    assert serialize(manifest)==serialize(build_manifest(*sources))
    assert serialize(manifest)==(ROOT/"tests/phase6_golden/book-context-manifest-v1.json").read_text()
    assert [v["chapter_id"] for v in manifest["chapters"]]==["ch-0001","ch-0002"]
    assert len(manifest["recurring_terms"])==4
    assert len(manifest["proper_names"])==1
    assert all("text" not in chapter for chapter in manifest["chapters"])

def test_manifest_preserves_publisher_readings_and_name_separation(manifest):
    ruby={v["id"]:v for c in manifest["chapters"] for v in c["publisher_ruby"]}
    assert ruby["ch-0001-b-0004-r-0001"]["reading"]=="おもてぶたい"
    assert ruby["ch-0002-b-0002-r-0001"]["reading"]=="ゆきの"
    assert manifest["proper_names"][0]["evidence_kind"]=="publisher_ruby_name"
    assert manifest["proper_names"][0]["sense_ids"]==[]

def test_edited_manifest_is_explicit_and_exports_valid_registries(manifest,edited,sources):
    validate_edited_manifest(manifest,edited)
    term,summ=export_registries(manifest,edited,sources[1],sources[3])
    assert serialize(term)==(ROOT/"tests/phase6_golden/exported-terminology-registry-v1.json").read_text()
    assert serialize(summ)==(ROOT/"tests/phase6_golden/exported-summary-registry-v1.json").read_text()
    assert term["decisions"][0]["approved_term"]=="public arena"
    assert summ["decisions"][1]["summary"]=="Yukino and turning around are observed."
    assert all(v["provenance"]=="user" for v in term["decisions"]+summ["decisions"])

def test_augmentation_matches_all_items_and_golden(edited):
    requests=load("artifacts/phase5/run-a/requests.json")
    report=build_augmentation(requests,edited,include_previous=True)
    assert serialize(report)==(ROOT/"tests/phase6_golden/context-augmentation-v1.json").read_text()
    assert [v["item_id"] for v in report["results"]]==[f"study-item-{n:04d}" for n in range(1,6)]
    assert report["results"][2]["effective_terminology"]=="public arena"
    assert report["results"][3]["evidence_kind"]=="publisher_ruby_name"
    assert [v["inclusion_reason"] for v in report["results"][3]["summaries"]]==["previous","target"]

def test_target_only_augmentation_excludes_previous(edited):
    value=build_augmentation(load("artifacts/phase5/run-a/requests.json"),edited)
    assert all(all(s["inclusion_reason"]=="target" for s in r["summaries"]) for r in value["results"])

def test_augmentation_budgets_exclude_complete_summaries_with_safe_diagnostics(edited):
    value=build_augmentation(load("artifacts/phase5/run-a/requests.json"),edited,
                             include_previous=True,record_budget=1,character_budget=20)
    assert all(result["summaries"]==[] for result in value["results"])
    assert all(value["diagnostics"][n]["id"]==f"context-augmentation-diagnostic-{n+1:04d}"
               for n in range(len(value["diagnostics"])))
    assert {item["reason"] for item in value["diagnostics"]}=={"budget-exclusion"}

def test_repeated_publisher_ruby_occurrences_remain_one_bounded_result(edited):
    value=build_augmentation(load("artifacts/phase5/run-a/requests.json"),edited)
    table=value["results"][2]
    assert table["occurrence_ids"]==[
        "study-item-0003-occ-0001","study-item-0003-occ-0002"
    ]
    assert table["effective_terminology"]=="public arena"

@pytest.mark.parametrize("mutation,message",[
    (lambda v:v["chapters"][0].update(source_path="changed"),"Protected"),
    (lambda v:v["proper_names"][0].update(authoritative_reading="wrong"),"Protected"),
    (lambda v:v["terminology_decisions"][0].update(approved_term="<script>"),"Unsafe"),
    (lambda v:v["terminology_decisions"][0].update(reviewer=""),"Missing"),
])
def test_invalid_edits_are_rejected(manifest,edited,mutation,message):
    value=copy.deepcopy(edited); mutation(value); value=rehash_manifest(value)
    with pytest.raises(ContextManifestError,match=message): validate_edited_manifest(manifest,value)

def test_terminology_summary_conflict_is_rejected(manifest,edited):
    value=copy.deepcopy(edited)
    value["summary_decisions"][0]["summary"]="Good weather is observed."
    value=rehash_manifest(value)
    with pytest.raises(ContextManifestError,match="conflicts"): validate_edited_manifest(manifest,value)

def test_disabled_and_failure_preserve_phase5_bytes():
    requests=load("artifacts/phase5/run-a/requests.json")
    plan=load("artifacts/phase5/enriched-plan/run-a/annotation-plan.json")
    for reason in (None,"corrupt-manifest"):
        report,out_requests,out_plan=disabled_context(requests,plan,reason)
        assert report["results"]==[]
        assert serialize(out_requests)==serialize(requests)
        assert serialize(out_plan)==serialize(plan)

def test_cli_fallback_preserves_exact_bytes(tmp_path):
    requests=ROOT/"artifacts/phase5/run-a/requests.json"
    plan=ROOT/"artifacts/phase5/enriched-plan/run-a/annotation-plan.json"
    subprocess.run([str(ROOT/".venv/bin/python"),str(ROOT/"scripts/build_context_manifest.py"),
        "fallback",str(requests),str(plan),str(tmp_path/"report.json"),
        str(tmp_path/"requests.json"),str(tmp_path/"plan.json"),"--reason","stale-manifest"],check=True,cwd=ROOT)
    assert (tmp_path/"requests.json").read_bytes()==requests.read_bytes()
    assert (tmp_path/"plan.json").read_bytes()==plan.read_bytes()
