.PHONY: clean_notebooks wheel install tests check_version dist check_dist upload_test upload bump release create-release docker docker_upload

PYCACHE := $(shell find . -name '__pycache__')
EGGS := $(wildcard *.egg-info)
CURRENT_VERSION := $(shell awk '/current_version =/ {print substr($$3, 2, length($$3)-2)}' pyproject.toml)


clean:
	@echo "=> Cleaning"
	@rm -fr build dist $(EGGS) $(PYCACHE)

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
	
create-release:
	@gh release create v$(CURRENT_VERSION) \
		dist/ocp_tessellate-$(CURRENT_VERSION).tar.gz \
		dist/ocp_tessellate-$(CURRENT_VERSION)-py3-none-any.whl \
		--title "ocp_tessellate-$(CURRENT_VERSION)" \
		--notes "v$(CURRENT_VERSION)" \
		--target main

install: dist
	@echo "=> Installing ocp-tessellate"
	@pip install --upgrade .

check_dist:
	@twine check dist/*

upload:
	@twine upload dist/*

