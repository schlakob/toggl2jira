"""
Configuration management for toggl2jira.
"""

from os import environ

import dotenv


class Config:
    """
    Configuration for toggl2jira loaded from a dotenv file.
    """

    def __init__(self, config_file: str) -> None:
        raw_config = {**dotenv.dotenv_values(config_file), **environ}

        self.jira_endpoint = raw_config.get("JIRA_URL", "")
        if len(self.jira_endpoint) == 0:
            raise RuntimeError("JIRA_URL is required.")

        self.jira_access_token = raw_config.get("JIRA_ACCESS_TOKEN", "")
        if len(self.jira_access_token) == 0:
            raise RuntimeError("JIRA_ACCESS_TOKEN is required.")

        self.jira_project_slug = raw_config.get("JIRA_PROJECT_SLUG", "")
        if len(self.jira_project_slug) == 0:
            raise RuntimeError("JIRA_PROJECT_SLUG is required.")

        self.toggl_endpoint = raw_config.get("TOGGL_URL", "https://api.track.toggl.com")
        if len(self.toggl_endpoint) == 0:
            raise RuntimeError("TOGGL_URL is required.")

        self.toggl_api_key = raw_config.get("TOGGL_API_KEY", "")
        if len(self.toggl_api_key) == 0:
            raise RuntimeError("TOGGL_API_KEY is required.")

        self.sync_window_size = int(raw_config.get("SYNC_WINDOW_SIZE", "1"))
        if self.sync_window_size < 0:
            raise RuntimeError("SYNC_WINDOW_SIZE is required and must be at least 1.")
