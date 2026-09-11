.PHONY: clean_notebooks wheel install tests typecheck check_version dist check_dist upload_test upload bump release create-release docker docker_upload

PYCACHE := $(shell find . -name '__pycache__')
EGGS := $(wildcard *.egg-info)
CURRENT_VERSION := $(shell awk '/current_version =/ {print substr($$3, 2, length($$3)-2)}' pyproject.toml)


clean:
	@echo "=> Cleaning"
	@rm -fr build dist $(EGGS) $(PYCACHE)

typecheck:
	@echo "=> Type checking (ty)"
	ty check ocp_tessellate tests/typing_conformance.py

prepare: clean
	git add .
	git status
	git commit -m "cleanup before release"

# Version commands

bump:
	@echo Current version: $(CURRENT_VERSION)
ifdef part
	bump-my-version bump $(part) --allow-dirty && grep current pyproject.toml
else ifdef version
	bump-my-version bump --allow-dirty --new-version $(version) && grep current pyproject.toml
else
	@echo "Provide part=major|minor|patch|release|build and optionally version=x.y.z..."
	exit 1
endif

# Dist commands

dist:
	@rm -f dist/*
	@python -m build -n

release:
	git add .
	git status
	git diff-index --quiet HEAD || git commit -m "Latest release: $(CURRENT_VERSION)"
	git tag -a v$(CURRENT_VERSION) -m "Latest release: $(CURRENT_VERSION)"
	
# Push, then a GitHub release under the tag `release` made. The push comes
# first because `gh release create` makes its own tag on GitHub's main when
# the tag is not there yet - and without the push that was the previous
# release's main, so nine releases pointed at source without their changes.
# No `--target`: the tag exists and names the commit.
create-release:
	@for f in dist/ocp_tessellate-$(CURRENT_VERSION).tar.gz \
	         dist/ocp_tessellate-$(CURRENT_VERSION)-py3-none-any.whl; do \
	    test -f $$f || { echo "missing $$f - run make dist first"; exit 1; }; \
	done
	@git push
	@git push --tags
	@gh release create v$(CURRENT_VERSION) \
		dist/ocp_tessellate-$(CURRENT_VERSION).tar.gz \
		dist/ocp_tessellate-$(CURRENT_VERSION)-py3-none-any.whl \
		--title "ocp_tessellate-$(CURRENT_VERSION)" \
		--notes "v$(CURRENT_VERSION)"

install: dist
	@echo "=> Installing ocp-tessellate"
	@pip install --upgrade .

check_dist:
	@twine check dist/*

upload:
	@twine upload dist/*

