# Updating to a new Aider release

This fork keeps upstream Aider on its own `upstream` branch, so a new release merges into `develop` as a normal
three-way merge: the common base is the untouched 0.86.2 source, and this fork's changes to upstream files are
small hooks.

| Branch | Holds |
|---|---|
| `upstream` | Untouched `aider/` package of each imported aider-chat release, one commit per release |
| `develop` | This fork: upstream plus the native tool calling, agent mode and their tests |

## Steps

1. Import the release into `upstream` from a separate worktree:

   ```
   git worktree add ../aider-upstream upstream
   python -m maintenance.import_upstream X.Y.Z --into ../aider-upstream
   git -C ../aider-upstream add -A
   git -C ../aider-upstream commit -m "Import aider-chat X.Y.Z from PyPI"
   git -C ../aider-upstream push
   git worktree remove ../aider-upstream
   ```

2. Merge it on a feature branch and refresh the pinned dependencies:

   ```
   git switch -c feature/upstream-X.Y.Z develop
   git merge upstream
   python -m maintenance.import_upstream X.Y.Z --pyproject pyproject.toml
   ```

3. Resolve conflicts. They can only appear in the upstream files this fork hooks into: `aider/models.py`,
   `aider/coders/base_coder.py`, `aider/coders/__init__.py`, `aider/args.py`, `aider/main.py` and
   `aider/commands.py`. Keep upstream's code and re-apply the hook lines.
4. Run the tests and a short real-model check (`python -m evals.run_evals --tasks fix-discount --sandbox`), then
   open a pull request into `develop` and release as usual.

## Notes

- `import_upstream` uses only the standard library and reads the release from PyPI's JSON API.
- The `upstream` branch starts at this repository's first commit, the untouched 0.86.2 source, which is why git
  can find the merge base.
