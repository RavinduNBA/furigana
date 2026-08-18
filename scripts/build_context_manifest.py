#!/usr/bin/env python3
import argparse
from pathlib import Path
from furiganalyse.book_context import serialize
from furiganalyse.context_manifest import *

def write(path, value):
    target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(serialize(value),encoding="utf-8")

def main():
    parser=argparse.ArgumentParser(); commands=parser.add_subparsers(dest="command",required=True)
    build=commands.add_parser("build")
    for name in ("index","evidence","terminology","packets","summaries","output"): build.add_argument(name)
    validate=commands.add_parser("validate")
    for name in ("original","edited"): validate.add_argument(name)
    export=commands.add_parser("export")
    for name in ("original","edited","evidence","packets","terminology_output","summary_output"): export.add_argument(name)
    augment=commands.add_parser("augment")
    for name in ("requests","manifest","output"): augment.add_argument(name)
    augment.add_argument("--include-previous",action="store_true")
    augment.add_argument("--record-budget",type=int,default=2)
    augment.add_argument("--character-budget",type=int,default=500)
    fallback=commands.add_parser("fallback")
    for name in ("requests","plan","report","requests_output","plan_output"): fallback.add_argument(name)
    fallback.add_argument("--reason")
    rehash=commands.add_parser("rehash")
    for name in ("input","output"): rehash.add_argument(name)
    args=parser.parse_args()
    if args.command=="build":
        write(args.output,build_manifest(*[load_json(getattr(args,n)) for n in ("index","evidence","terminology","packets","summaries")]))
    elif args.command=="validate":
        validate_edited_manifest(load_json(args.original),load_json(args.edited))
    elif args.command=="export":
        term,summ=export_registries(load_json(args.original),load_json(args.edited),load_json(args.evidence),load_json(args.packets))
        write(args.terminology_output,term); write(args.summary_output,summ)
    elif args.command=="augment":
        write(args.output,build_augmentation(load_json(args.requests),load_json(args.manifest),include_previous=args.include_previous,record_budget=args.record_budget,character_budget=args.character_budget))
    elif args.command=="rehash":
        write(args.output,rehash_manifest(load_json(args.input)))
    else:
        report,requests,plan=disabled_context(load_json(args.requests),load_json(args.plan),args.reason)
        write(args.report,report); write(args.requests_output,requests); write(args.plan_output,plan)
if __name__=="__main__": main()
