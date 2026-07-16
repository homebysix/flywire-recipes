#!/usr/local/autopkg/python

import json
import os
from typing import Any

from autopkglib import APLooseVersion, ProcessorError, URLGetter

__all__ = ["GitHubTagsInfoProvider"]

GITHUB_API_URL = "https://api.github.com"


class GitHubTagsInfoProvider(URLGetter):
    """
    Finds the newest (or a pinned) release tag for a GitHub repo. Optionally handles
    tags that are prefixed (e.g. 'v1.0.0' or 'release/1.0.0').
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
            "description": "Prefix that release tags start with.",
        },
        "tag_version": {
            "required": False,
            "description": "A specific version to pin, e.g. '1.0.0'. If empty, the newest version is selected.",
        },
    }
    output_variables = {
        "version": {
            "description": "The resolved version string, with the tag prefix stripped.",
        },
        "url": {
            "description": "URL to the source tarball for the resolved tag.",
        },
    }

    def list_tag_versions(
        self, github_repo: str, tag_prefix: str, headers: dict[str, str]
    ) -> list[str]:
        """Downloads the repo's tags and returns the versions matching tag_prefix."""
        url = f"{GITHUB_API_URL}/repos/{github_repo}/tags?per_page=100"
        response = self.download(url, headers=headers)
        try:
            tags: list[dict[str, Any]] = json.loads(response)
        except (ValueError, TypeError) as e:
            self.output(f"JSON response was: {response}")
            raise ProcessorError(f"JSON format error: {e}")

        versions = [
            tag["name"][len(tag_prefix) :]
            for tag in tags
            if tag["name"].startswith(tag_prefix)
        ]
        if not versions:
            if tag_prefix:
                raise ProcessorError(
                    f"No tags starting with '{tag_prefix}' found for {github_repo}"
                )
            raise ProcessorError(f"No tags found for {github_repo}")
        return versions

    def main(self) -> None:
        github_repo: str = self.env["github_repo"]
        tag_prefix: str = self.env.get("tag_prefix", "")
        pinned_version: str = self.env.get("tag_version", "")

        headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
        github_token = os.environ.get("GITHUB_TOKEN")
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"

        versions = self.list_tag_versions(github_repo, tag_prefix, headers)

        if pinned_version:
            if pinned_version not in versions:
                raise ProcessorError(
                    f"Tag '{tag_prefix}{pinned_version}' not found for {github_repo}"
                )
            version = pinned_version
        else:
            version = max(versions, key=APLooseVersion)

        self.env["version"] = version
        self.env["url"] = (
            f"https://github.com/{github_repo}/archive/refs/tags/"
            f"{tag_prefix}{version}.tar.gz"
        )
        self.output(f"Resolved {tag_prefix}{version} -> {self.env['url']}")


if __name__ == "__main__":
    PROCESSOR = GitHubTagsInfoProvider()
    PROCESSOR.execute_shell()
