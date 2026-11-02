# Updating to a new Aider release

This fork keeps each imported upstream Aider release as a tag, `upstream-X.Y.Z`, so a new release merges into
`develop` as a normal three-way merge: the common base is the untouched 0.86.2 source, and this fork's changes to
upstream files are small hooks. The repository has only `main` and `develop` as long-lived branches; an import
uses a temporary branch that is deleted once its tag is pushed.

| Ref | Holds |
|---|---|
| `upstream-X.Y.Z` tags | Untouched `aider/` package of each imported aider-chat release, one commit per release, each on top of the previous one |
| `develop` | This fork: upstream plus the native tool calling, agent mode and their tests |

## Steps

1. Import the release on a temporary branch started from the latest `upstream-*` tag (the newest in
   `git tag --list 'upstream-*' --sort=-v:refname`), in a separate worktree, then tag it and drop the branch:

   ```
   git worktree add -b upstream-import ../aider-upstream upstream-<latest>
   python -m maintenance.import_upstream X.Y.Z --into ../aider-upstream
   git -C ../aider-upstream add -A
   git -C ../aider-upstream commit -m "Import aider-chat X.Y.Z from PyPI"
   git tag -a upstream-X.Y.Z -m "aider-chat X.Y.Z from PyPI" upstream-import
   git push origin upstream-X.Y.Z
   git worktree remove ../aider-upstream
   git branch -D upstream-import
   ```

2. Merge the tag on a feature branch and refresh the pinned dependencies:

   ```
   git switch -c feature/upstream-X.Y.Z develop
   git merge upstream-X.Y.Z
   python -m maintenance.import_upstream X.Y.Z --pyproject pyproject.toml
   ```

3. Resolve conflicts. They can only appear in the upstream files this fork hooks into: `aider/models.py`,
   `aider/coders/base_coder.py`, `aider/coders/__init__.py`, `aider/args.py`, `aider/main.py` and
   `aider/commands.py`. Keep upstream's code and re-apply the hook lines.
4. Run the tests and a short real-model check (`python -m evals.run_evals --tasks fix-discount --sandbox`), then
   open a pull request into `develop` and release as usual.

## Notes

- `import_upstream` uses only the standard library and reads the release from PyPI's JSON API.
- `upstream-0.86.2` is the 0.86.2 import, made on top of this repository's first commit; that shared first
  commit is why git can find the merge base. Until 2026-11-02 the same commits lived on an `upstream` branch; it
  was replaced by the tags.
