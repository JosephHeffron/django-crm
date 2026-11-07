"""The two website-only shortcuts, and the one rule they share.

`scripts/change-scope.sh` decides whether a change touches only the
public website. CI uses it to run just the website's checks on such a
pull request, and `scripts/deploy.sh --website-only` uses it to refuse
anything that would need an image rebuild (plan D6.4 and D6.5,
docs/decisions/0017-the-website-lives-in-this-repository.md).

The deploy tests run the real script end to end in a throwaway set of
git repositories: an origin, a "server" checkout that the script
deploys in, and a "developer" clone that pushes new commits. `curl`,
`podman` and `podman-compose` are stubs on PATH that record how they
were called, so the tests can assert that a website-only deploy never
touches a container.
"""

import re
import subprocess
from pathlib import Path
from unittest import skipIf

from django.conf import settings
from django.test import SimpleTestCase

from apps.core.tests._deploy import (
    GIT,
    GOOD_PAGE,
    SCOPE,
    DeployHarness,
    skips_certificate_checks,
)

ROOT = Path(settings.BASE_DIR)
CI = ROOT / ".github" / "workflows" / "ci.yml"


def scope(paths):
    result = subprocess.run(
        ["sh", str(SCOPE)], input=paths, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


class ChangeScopeTests(SimpleTestCase):
    def test_website_content_alone_is_website(self):
        self.assertEqual(scope("website/index.html\n"), "website")
        self.assertEqual(scope("website/about.html\nwebsite/assets/css/site.css\n"), "website")
        self.assertEqual(scope("website/assets/img/a b.jpg\n"), "website")

    def test_a_last_line_without_a_newline_still_counts(self):
        self.assertEqual(scope("website/index.html"), "website")
        self.assertEqual(scope("website/index.html\napps/x.py"), "full")

    def test_partials_are_never_a_shortcut(self):
        # Django reads them for /book/ (ADR 0017).
        self.assertEqual(scope("website/partials/header.html\n"), "full")
        self.assertEqual(scope("website/index.html\nwebsite/partials/footer.html\n"), "full")

    def test_anything_outside_website_is_full(self):
        for path in (
            "Caddyfile",
            "compose.prod.yml",
            ".github/workflows/ci.yml",
            "requirements.txt",
            "apps/core/views.py",
            "scripts/change-scope.sh",
        ):
            with self.subTest(path=path):
                self.assertEqual(scope(f"website/index.html\n{path}\n"), "full")
                self.assertEqual(scope(f"{path}\nwebsite/index.html\n"), "full")

    def test_a_lookalike_prefix_is_full(self):
        self.assertEqual(scope("websites/index.html\n"), "full")
        self.assertEqual(scope("website\n"), "full")
        self.assertEqual(scope("docs/website/index.html\n"), "full")

    def test_no_paths_at_all_is_full(self):
        # Never skip anything on not knowing.
        self.assertEqual(scope(""), "full")
        self.assertEqual(scope("\n\n"), "full")

    def test_a_long_list_is_read_to_the_end(self):
        # An early exit would SIGPIPE the writer, which fails the step
        # under GitHub Actions' `set -o pipefail`.
        # About 850 KB, well past a pipe's buffer, so a reader that quit
        # at the first line would leave the writer to die of SIGPIPE.
        result = subprocess.run(
            ["bash", "-o", "pipefail", "-c", f'seq 1 50000 | sed "s|^|apps/file|" | sh "{SCOPE}"'],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "full")


class WorkflowTests(SimpleTestCase):
    """Read as text: the project has no YAML parser, and these are
    properties of the file a reviewer should be able to see in it."""

    def setUp(self):
        self.workflow = CI.read_text()

    def test_the_trigger_has_no_path_filters(self):
        # A required check that a path filter stops from running is
        # reported as missing, and the PR can never merge (plan D6.5).
        self.assertIsNone(re.search(r"^\s*paths(-ignore)?\s*:", self.workflow, re.MULTILINE))

    def test_the_scope_comes_from_the_shared_rule_with_renames_split(self):
        self.assertIn("git diff --name-only --no-renames HEAD^1 HEAD", self.workflow)
        self.assertIn("sh scripts/change-scope.sh", self.workflow)
        self.assertIn("fetch-depth: 2", self.workflow)

    def test_the_full_steps_run_unless_the_scope_is_exactly_website(self):
        # `!= 'website'`, not `== 'full'`: if the scope step ever
        # produced nothing, the full suite still runs.
        steps = self.workflow.split("- name: ")
        for name in ("Migration check", "Apply migrations", "Test\n"):
            step = next(s for s in steps if s.startswith(name))
            self.assertIn("if: steps.scope.outputs.scope != 'website'", step, name)

    def test_website_changes_still_run_the_website_checks(self):
        step = next(s for s in self.workflow.split("- name: ") if s.startswith("Test (website"))
        self.assertIn("if: steps.scope.outputs.scope == 'website'", step)
        self.assertIn("manage.py test apps.core.tests.test_website", step)

    def test_lint_and_caddy_always_run(self):
        for name in ("Lint", "Install Caddy"):
            step = next(s for s in self.workflow.split("- name: ") if s.startswith(name))
            self.assertNotIn("if:", step.split("run:")[0], name)


@skipIf(not GIT, "needs git")
class WebsiteOnlyDeployTests(DeployHarness, SimpleTestCase):
    # --- the path that should work ----------------------------------

    def test_a_website_change_goes_live_without_touching_a_container(self):
        target = self.push("copy", {"website/about.html": "<p>new about</p>\n"})
        result = self.deploy("--website-only", "main")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.head(), target)
        self.assertEqual((self.server / "website/about.html").read_text(), "<p>new about</p>\n")
        self.assertEqual(self.state(), self.deployed, "rollback target not recorded")
        self.assertEqual(self.log("containers"), "", "a website-only deploy ran podman")
        self.assertIn("website healthy", result.stdout)

    def test_the_check_goes_through_caddy_on_this_host(self):
        self.push("copy", {"website/about.html": "<p>x</p>\n"})
        self.deploy("--website-only", "main")
        call = self.log("curl")
        self.assertIn("--resolve example.test:443:127.0.0.1", call)
        self.assertIn("https://example.test/", call)
        self.assertFalse(skips_certificate_checks(call), "the certificate must be checked")

    def test_a_sha_deploys_as_well_as_a_branch(self):
        target = self.push("copy", {"website/about.html": "<p>y</p>\n"})
        result = self.deploy("--website-only", target)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.head(), target)

    # --- what it refuses --------------------------------------------

    def assertRefused(self, result, why):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(self.head(), self.deployed, f"{why}: the checkout moved")
        self.assertEqual(self.log("containers"), "")
        self.assertIsNone(self.state())

    def test_a_change_with_code_in_it_is_refused(self):
        self.push("mixed", {"website/about.html": "<p>z</p>\n", "apps/app.py": "VALUE = 2\n"})
        result = self.deploy("--website-only", "main")
        self.assertRefused(result, "code change")
        self.assertIn("Use a full deploy instead", result.stderr)

    def test_a_partials_change_is_refused(self):
        self.push("partial", {"website/partials/header.html": "<header>new</header>\n"})
        self.assertRefused(self.deploy("--website-only", "main"), "partials change")

    def test_code_moved_into_website_is_refused(self):
        # The reason for --no-renames: without it only the new path
        # under website/ is listed, and the removal from apps/ is not.
        self.git(self.dev, "mv", "apps/app.py", "website/app.js")
        self.push("move")
        self.assertRefused(self.deploy("--website-only", "main"), "rename into website/")

    def test_deploying_what_is_already_deployed_is_refused(self):
        self.assertRefused(self.deploy("--website-only", self.deployed), "no change")

    def test_a_dirty_checkout_is_refused(self):
        self.push("copy", {"website/about.html": "<p>q</p>\n"})
        (self.server / "website/about.html").write_text("edited on the server\n")
        result = self.deploy("--website-only", "main")
        self.assertEqual(result.returncode, 1)
        self.assertIn("uncommitted changes", result.stderr)
        self.assertEqual(self.head(), self.deployed)

    def test_an_unknown_ref_is_refused(self):
        self.assertRefused(self.deploy("--website-only", "no-such-branch"), "unknown ref")

    def test_the_flag_without_a_ref_is_a_usage_error(self):
        result = self.deploy("--website-only")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Usage:", result.stderr)

    # --- a deploy whose page check fails is reverted ----------------

    def test_a_page_missing_the_shared_header_is_reverted(self):
        self.push("broken", {"website/index.html": "<main>no header</main>\n"})
        result = self.deploy("--website-only", "main")
        self.assertRefused(result, "broken page")
        self.assertIn("missing the shared header", result.stdout)
        self.assertIn("Restored", result.stderr)
        self.assertEqual((self.server / "website/index.html").read_text(), GOOD_PAGE)

    def test_an_unprocessed_include_counts_as_broken(self):
        page = '{{include "/partials/header.html"}}<header class="site-header"></header>\n'
        self.push("raw include", {"website/index.html": page})
        result = self.deploy("--website-only", "main")
        self.assertRefused(result, "raw include")
        self.assertIn("unprocessed {{include", result.stdout)

    def test_an_unreachable_site_is_reverted_and_blamed_on_caddy(self):
        self.push("copy", {"website/about.html": "<p>r</p>\n"})
        result = self.deploy("--website-only", "main", STUB_CURL_FAIL="1")
        self.assertRefused(result, "unreachable")
        self.assertIn("also fails", result.stderr)
        self.assertIn("podman logs", result.stderr)

    def test_no_website_host_in_env_fails_closed(self):
        (self.server / ".env").write_text("CRM_HOST=crm.example.test\n")
        self.push("copy", {"website/about.html": "<p>s</p>\n"})
        result = self.deploy("--website-only", "main")
        self.assertRefused(result, "no WEBSITE_HOST")
        self.assertIn("WEBSITE_HOST is not set", result.stderr)
