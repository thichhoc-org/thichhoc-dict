.PHONY: help download stage1 retier stage2-match stage2-llm stage2-refresh promote ab validate test build stats clean clean-all tests-regen entry
.DEFAULT_GOAL := help

PROJECT ?= dict-en-vi
ENTRIES  = $(PROJECT)/data/entries
PIPELINE = $(PROJECT)/pipeline
TESTS    = $(PROJECT)/tests
OUT     ?= build
DATE    ?= $(shell date -u +%Y-%m-%d)

# Derived from git, not left blank. The version is stamped into the dictionary
# itself — the attribution entry a reader finds by looking up "thichhoc", and
# the OPF uid — so a local build with no VERSION= silently shipped v0.9.0's
# .mobi labelled "bản 0.1.0", the builder default. CI never had the bug because
# it passes --version from the tag name.
#
# `git describe --dirty` is deliberate: a build off a tag gets 0.9.0, and one
# taken three commits later gets 0.9.0-3-gabc123-dirty, which is the honest
# answer to "which build is this?" and cannot be mistaken for a release.
VERSION ?= $(shell git describe --tags --dirty 2>/dev/null | sed 's/^v//')

UV = uv run

help:
	@echo "thichhoc-dict — PROJECT=$(PROJECT)"
	@echo
	@echo "  make download     fetch upstream corpora into data/source/raw/ (gitignored)"
	@echo "  make stage1       run Stage 1: lemmas -> IPA -> inflections -> entry store"
	@echo "  make retier       re-apply junk filter + tier ranking, keeping senses"
	@echo "  make stage2-refresh  re-cut a tier as aligned {en,vi} pairs (costs money)"
	@echo "  make promote      write a Stage 2 output into the entry store"
	@echo "  make validate     check the entry store against the schema"
	@echo "  make test         inflection release gate (must pass 100%)"
	@echo "  make build        build StarDict + Kobo + MOBI source into $(OUT)/"
	@echo "  make stats        coverage report"
	@echo "  make release      validate + test + build, in that order"
	@echo
	@echo "  make clean        remove build output"
	@echo "  make clean-all    also remove downloaded corpora and intermediates"

download:
	$(UV) python $(PROJECT)/data/source/download.py

# Stage 1 is deterministic and free — re-running it from scratch is the normal
# way to pick up a pipeline change (plan §2).
stage1:
	cd $(PIPELINE) && $(UV) python s1_lemmas.py
	cd $(PIPELINE) && $(UV) python s1_ipa.py
	cd $(PIPELINE) && $(UV) python s1_inflect.py
	cd $(PIPELINE) && $(UV) python s1_build_skeleton.py

# Re-apply the headword policy (junk filter + tier ranking) to the entry store
# without rebuilding it — stage1 would rebuild from WordNet and discard senses.
retier:
	cd $(PIPELINE) && $(UV) python s1_retier.py $(if $(GO),,--dry-run)

# Stage 2a is free and deterministic — always run it before spending on Stage 2b,
# since every entry it fills is one the LLM never sees.
stage2-match:
	cd $(PIPELINE) && $(UV) python s2_match_vi.py

# Costs money. Defaults to a dry run; pass GO=1 to actually submit.
#   make stage2-llm TIER=1 LIMIT=100        # preview, no API call
#   make stage2-llm TIER=1 LIMIT=100 GO=1   # submit
TIER     ?=
LIMIT    ?=
PROVIDER ?= claude
stage2-llm:
	cd $(PIPELINE) && $(UV) python s2_llm.py --provider $(PROVIDER) \
		$(if $(TIER),--tier $(TIER),) $(if $(LIMIT),--limit $(LIMIT),) \
		$(if $(GO),,--dry-run)

# Re-translate a tier that already has senses, replacing them, so the entries
# come back as aligned {en, vi} pairs. Costs money; --dry-run unless GO=1.
#
# This exists because the ordinary stage2-llm can never reach a partially
# filled entry: it only selects `not senses_vi`, so the noun `spring`, which
# Wiktionary answered with two of its three senses, was permanently out of the
# pool and could never acquire "suối".
#
#   make stage2-refresh PROVIDER=ark TIER=1              # preview + forecast
#   make stage2-refresh PROVIDER=ark TIER=1 GO=1         # submit
#
# The cache is deliberately a separate file: the existing llm-cache-ark.jsonl
# holds bare-list results for these same ids, and reusing it would shadow every
# new paired answer with the old unpaired one.
GROUP ?= 20
# IN defaults to the entry store — what the build actually ships — rather than
# a work/ snapshot, which goes stale the moment `make retier` changes the tiers.
IN ?= ../data/entries
stage2-refresh:
	cd $(PIPELINE) && $(UV) python s2_llm.py --provider $(PROVIDER) $(if $(REFRESH),--refresh,) $(if $(PAIRED),--paired,) \
		--in $(IN) \
		--out ../data/work/s2c-paired.jsonl \
		--cache ../data/work/llm-cache-$(PROVIDER)$(if $(MODEL),-$(MODEL),)-paired.jsonl \
		--group-size $(GROUP) $(if $(CONC),--concurrency $(CONC),) $(if $(MODEL),--model $(MODEL),) \
		$(foreach t,$(TIER),--tier $(t)) $(if $(LIMIT),--limit $(LIMIT),) \
		$(if $(GO),,--dry-run)

# Promote a Stage 2 output into the sharded entry store that builds read from.
promote:
	cd $(PIPELINE) && $(UV) python s1_build_skeleton.py \
		--in ../data/work/$(or $(FROM),s2c-paired.jsonl)

# Same entries through two providers, then a side-by-side table.
#   make ab LIMIT=100        # preview, no API call
#   make ab LIMIT=100 GO=1   # run both
ab:
	cd $(PIPELINE) && $(UV) python s2_ab_test.py --limit $(or $(LIMIT),100) \
		$(if $(GO),,--dry-run)

validate:
	$(UV) thichhoc-dict validate $(ENTRIES)

test:
	cd $(TESTS) && $(UV) python test_inflection.py

# Regenerating the test list is deliberate and rare — the checked-in file is
# the contract. Only run this when adding newly reported failure cases.
tests-regen:
	cd $(TESTS) && $(UV) python make_inflection_tests.py

build:
	$(UV) thichhoc-dict build $(ENTRIES) --out $(OUT) --date $(DATE) \
		$(if $(VERSION),--version $(VERSION),)

stats:
	$(UV) python qa/report_stats.py $(ENTRIES)

release: validate test build stats

clean:
	rm -rf $(OUT)

clean-all: clean
	rm -rf $(PROJECT)/data/source/raw $(PROJECT)/data/work .tools
