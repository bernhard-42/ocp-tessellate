# Release documentation

## Release process

1. Clean environment

    ```bash
    make clean    # delete build, dist, egg-info and __pycache__
    ```

    `make prepare` runs `make clean` and commits everything (`git add .`) as "cleanup before release"; only use it when that is what you want.

2. Bump the version of ocp_tessellate

    ```bash
    make bump part=major|minor|patch
    ```

    or set a version explicitly:

    ```bash
    make bump version=major.minor.patch
    ```

    `part` wins when both are given. The version is `major.minor.patch` only (`serialize` in `[tool.bumpversion]`), so release candidates and `part=build|release` are not supported. The bump changes `pyproject.toml` and `ocp_tessellate/_version.py`.

3. Add the changes to `CHANGELOG.md`

    A new section at the top, `## vX.Y.Z (YYYY-MM-DD)`, with **Fixes**, **Features**, **Changes** or **Removals** as needed.

4. Create the distribution

    ```bash
    make dist
    make check_dist   # twine check
    ```

5. Commit and tag the release

    ```bash
    make release
    ```

    Commits all changes (`git add .`) as "Latest release: X.Y.Z" and creates the annotated tag `vX.Y.Z`. Nothing is pushed.

6. Deploy to PyPI

    ```bash
    make upload
    ```

7. Push the repo and the tag, create the GitHub release

    ```bash
    make create-release
    ```

    Checks that both files of this version are in `dist/`, pushes `main`, pushes only the tag of this release and creates the GitHub release with the wheel and the sdist. Do not use `git push --tags`: 16 old local tags (v1.0.0rc10 to v3.2.1) differ from the ones on GitHub, so the push is rejected. The push has to come before `gh release create`, otherwise GitHub creates the tag itself on the previous state of `main` (see the comment in the `Makefile`).
