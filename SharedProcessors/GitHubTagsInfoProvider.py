#!/usr/local/autopkg/python
#
# MIT License
#
# Copyright (c) 2026 Flywire
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from datetime import datetime
from typing import Any

import autopkglib.github
from autopkglib import Processor, ProcessorError

__all__ = ["GitHubTagsInfoProvider"]


class GitHubTagsInfoProvider(Processor):
    """
    Finds the most recently committed (or a pinned) tag for a GitHub repo. Tags are
    not assumed to be versions, so recency is determined by each tag's commit date
    rather than by name (tag list order and tag names are not reliable indicators of
    recency).
    """

    description = __doc__

    input_variables = {
        "github_repo": {
            "required": True,
            "description": "GitHub repo in 'owner/name' form, e.g. 'autopkg/recipes'.",
        },
        "tag_prefix": {
            "required": False,
            "default": "",
            "description": "Prefix that tags must start with to be considered.",
        },
        "pinned_tag": {
            "required": False,
            "description": "A specific, full tag name to pin, e.g. 'v1.0.0'. If empty, the most recently committed tag is selected.",
        },
        "curl_opts": {
            "required": False,
            "description": "Optional array of curl options to include with the download request.",
        },
        "CURL_PATH": {
            "required": False,
            "description": "Path to curl binary. Defaults to /usr/bin/curl.",
            "default": "/usr/bin/curl",
        },
        "GITHUB_URL": {
            "required": False,
            "description": (
                "If your organization has an internal GitHub instance "
                "set this value to your internal GitHub URL "
                "ie. 'https://git.internal.corp.com/api/v3'"
            ),
            "default": "https://api.github.com",
        },
        "GITHUB_TOKEN_PATH": {
            "required": False,
            "description": (
                "Path to a file containing your GitHub token. "
                "Can be a relative path or absolute path. "
                "ie. '~/.custom_gh_token' or '/path/to/token' "
                "NOTE: the AutoPkg preference 'GITHUB_TOKEN' "
                "takes precedence over this value."
            ),
            "default": "~/.autopkg_gh_token",
        },
    }
    output_variables = {
        "tag_name": {
            "description": "The resolved tag's full name.",
        },
        "url": {
            "description": "GitHub API URL for the resolved tag's ref.",
        },
        "tarball_url": {
            "description": "URL to the source tarball for the resolved tag.",
        },
        "zipball_url": {
            "description": "URL to the source zipball for the resolved tag.",
        },
        "commit_sha": {
            "description": "SHA of the commit the resolved tag points to.",
        },
        "commit_date": {
            "description": "ISO 8601 commit date.",
        },
        "node_id": {
            "description": "GraphQL node ID of the resolved tag.",
        },
    }

    def get_github_session(self) -> autopkglib.github.GitHubSession:
        return autopkglib.github.GitHubSession(
            self.env["CURL_PATH"],
            self.env.get("curl_opts"),
            self.env["GITHUB_URL"],
            self.env["GITHUB_TOKEN_PATH"],
        )

    def list_tags(
        self, github: autopkglib.github.GitHubSession, github_repo: str, tag_prefix: str
    ) -> list[dict[str, Any]]:
        """Fetches the repo's tags and returns those matching tag_prefix."""
        tags, status = github.call_api(
            f"/repos/{github_repo}/tags", query="per_page=100"
        )
        if status != 200:
            raise ProcessorError(f"Unexpected GitHub API status code {status}.")

        matching_tags = [tag for tag in tags if tag["name"].startswith(tag_prefix)]
        if not matching_tags:
            if tag_prefix:
                raise ProcessorError(
                    f"No tags starting with '{tag_prefix}' found for {github_repo}"
                )
            raise ProcessorError(f"No tags found for {github_repo}")
        return matching_tags

    def get_commit_date(
        self, github: autopkglib.github.GitHubSession, commit_url: str
    ) -> str:
        """Fetches a commit and returns its committer date."""
        endpoint = commit_url.removeprefix(github.url)
        commit, status = github.call_api(endpoint)
        if status != 200:
            raise ProcessorError(f"Unexpected GitHub API status code {status}.")
        return commit["commit"]["committer"]["date"]

    def most_recent_tag(
        self, github: autopkglib.github.GitHubSession, tags: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Returns the tag whose commit has the most recent committer date."""
        for tag in tags:
            tag["_commit_date"] = self.get_commit_date(github, tag["commit"]["url"])
        return max(
            tags,
            key=lambda tag: datetime.fromisoformat(
                tag["_commit_date"].replace("Z", "+00:00")
            ),
        )

    def main(self) -> None:
        github_repo: str = self.env["github_repo"]
        tag_prefix: str = self.env.get("tag_prefix", "")
        pinned_tag: str = self.env.get("pinned_tag", "")

        github = self.get_github_session()

        tags = self.list_tags(github, github_repo, tag_prefix)

        if pinned_tag:
            resolved_tag = next(
                (tag for tag in tags if tag["name"] == pinned_tag), None
            )
            if resolved_tag is None:
                raise ProcessorError(f"Tag '{pinned_tag}' not found for {github_repo}")
            resolved_tag["_commit_date"] = self.get_commit_date(
                github, resolved_tag["commit"]["url"]
            )
        else:
            resolved_tag = self.most_recent_tag(github, tags)

        self.output(
            f"Resolved {resolved_tag['name']} ({resolved_tag['_commit_date']}) -> {self.env['url']}"
        )
        self.output(resolved_tag, 2)

        self.env["tag_name"] = resolved_tag["name"]
        self.env["url"] = (
            f"{github.url}/repos/{github_repo}/git/refs/tags/{resolved_tag['name']}"
        )
        self.env["tarball_url"] = resolved_tag["tarball_url"]
        self.env["zipball_url"] = resolved_tag["zipball_url"]
        self.env["commit_sha"] = resolved_tag["commit"]["sha"]
        self.env["commit_date"] = resolved_tag["_commit_date"]
        self.env["node_id"] = resolved_tag["node_id"]


if __name__ == "__main__":
    PROCESSOR = GitHubTagsInfoProvider()
    PROCESSOR.execute_shell()
