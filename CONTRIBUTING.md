# Contributing to RepoMind

Make changes on a branch and open a pull request targeting `main`. Keep commits focused and run the relevant checks before requesting a merge. The existing [CI workflow](.github/workflows/ci.yml) runs on pushes and pull requests.

## Required checks

Both GitHub Actions jobs must pass on the current pull request head before merging:

- `api`: Python lint, type checking, compilation, Compose validation, database migration, API tests, and evaluation metric tests.
- `web`: dependency audit, lint, type checking, component tests, production build, and browser test.

If either job fails, fix the issue on the branch and wait for both jobs to pass again. Update the branch with `main` and rerun CI if `main` moved after the checks started. Merge through the pull request after the required checks pass. Do not push directly to `main` or force-push it.

## GitHub repository rule

The workflow alone cannot stop a direct push or merge. A repository administrator must protect `main` in **Settings → Branches → Add branch protection rule** (or use an equivalent active ruleset) with these settings:

1. Branch name pattern: `main`.
2. **Require a pull request before merging**.
3. **Require status checks to pass before merging**, selecting the `api` and `web` checks from the `CI` GitHub Actions workflow.
4. **Require branches to be up to date before merging**.
5. **Do not allow bypassing the above settings**, including administrators.
6. Keep force pushes and branch deletion disabled.

After saving the rule, verify that GitHub marks `main` as protected and that a pull request with a pending or failing `api` or `web` check cannot merge. The rule must be active for these requirements to be enforced by GitHub.
