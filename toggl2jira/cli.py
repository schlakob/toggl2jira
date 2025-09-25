"""
Command line interface for toggl2jira.
"""

import logging
import math
import sys
from datetime import date, timedelta
from os import EX_DATAERR, EX_OK, EX_SOFTWARE, getcwd, path

import truststore
from dateutil import parser

from toggl2jira.config import Config
from toggl2jira.jira import Jira, JiraApi
from toggl2jira.toggl import Toggl, TogglApi


def main():
    """
    Main entrypoint for the CLI application.
    """

    logging.basicConfig(stream=sys.stdout, level=logging.INFO)
    truststore.inject_into_ssl()
    try:
        config_locations = [
            path.join(getcwd(), "toggl2jira.env"),
            path.join(path.expanduser("~"), ".config", "toggl2jira.env"),
            path.join(path.dirname(__file__), "toggl2jira.env"),
        ]

        config = None
        for location in config_locations:
            print(f"checking for config at {location}")
            if path.exists(location):
                config = Config(location)
                break
    except RuntimeError as e:
        logging.error("Could not load config (%s)", e)
        sys.exit(EX_DATAERR)

    # setup filters
    logging.info(
        "starting sync with window of %s days searching for %s",
        config.sync_window_size, config.jira_project_slug
    )
    to_date = date.today() + timedelta(days=1)
    from_date = to_date - timedelta(days=config.sync_window_size)

    # creating jira and toggl utilities
    jira_api = JiraApi(config.jira_endpoint, config.jira_access_token)
    jira = Jira(jira_api, config.jira_project_slug)
    toggl_api = TogglApi(config.toggl_endpoint, config.toggl_api_key)
    toggl = Toggl(toggl_api, config.jira_project_slug)

    # get jira user information
    logging.info("connecting to jira (%s)", config.jira_endpoint)
    jira_user = jira.get_user()
    logging.info("authenticated as %s", jira_user['name'])

    # get jira issues with relevant worklogs
    jira_issues = jira.get_issues_by_worklogs(jira_user, from_date, to_date)
    logging.info("found %s issues with relevant worklogs", len(jira_issues))

    # get all relevant jira worklogs from issues
    jira_worklogs = []
    for jira_issue in jira_issues:
        worklogs = jira.get_worklogs_from_issue(
            jira_issue, jira_user, from_date, to_date
        )
        jira_worklogs.extend(worklogs)

    # filter synced jira worklogs
    jira_worklogs_filtered = list(filter(jira.worklog_filter, jira_worklogs))
    logging.info(
        "found %s worklogs, %s of which will be synced",
        len(jira_worklogs), len(jira_worklogs_filtered)
    )
    for jira_worklog in jira_worklogs_filtered:
        logging.debug(
            "jira worklog [%s %s +%ss]",
            jira_worklog['issueKey'], jira_worklog['started'], jira_worklog['timeSpentSeconds']
        )

    # get toggl user information
    logging.info("connecting to toggl (%s)", config.toggl_endpoint)
    toggl_user = toggl.get_user()
    logging.info("authenticated as %s", toggl_user['email'])

    # get toggl time entries and convert them to worklogs
    toggl_time_entries = toggl.get_time_entries(from_date, to_date)
    toggl_worklogs = list(map(toggl.convert_time_entry_to_worklog, toggl_time_entries))

    # filter synced toggl worklogs
    toggl_worklogs_filtered = list(filter(toggl.worklog_filter, toggl_worklogs))
    logging.info(
        "found %s time entries, %s of which will be synced",
        len(toggl_time_entries), len(toggl_worklogs_filtered)
    )
    for worklog in toggl_worklogs_filtered:
        logging.debug(
            "toggl worklog [%s %s +%ss]",
            worklog['issueKey'], worklog['started'], worklog['timeSpentSeconds']
        )

    # determine worklogs that are already in sync
    worklogs_to_add = toggl_worklogs_filtered.copy()
    worklogs_to_delete = jira_worklogs_filtered.copy()
    already_synced_count = 0

    for toggl_worklog in toggl_worklogs_filtered:
        for jira_worklog in jira_worklogs_filtered:
            if (
                toggl_worklog["issueKey"] == jira_worklog["issueKey"]
                and parser.parse(toggl_worklog["started"])
                == parser.parse(jira_worklog["started"])
                and math.floor(toggl_worklog["timeSpentSeconds"] / 60)
                == math.floor(jira_worklog["timeSpentSeconds"] / 60)
            ):
                already_synced_count += 1
                worklogs_to_delete.remove(jira_worklog)
                worklogs_to_add.remove(toggl_worklog)
                break

    logging.info(
        "%s/%s toggl worklogs are already in sync",
        already_synced_count, len(toggl_worklogs_filtered)
    )
    logging.info(
        "%s jira worklogs to add, %s jira worklogs to delete",
        len(worklogs_to_add), len(worklogs_to_delete)
    )

    total_sync_operations = len(worklogs_to_add) + len(worklogs_to_delete)
    successful_sync_operations = 0

    # delete worklogs
    for worklog in worklogs_to_delete:
        logging.info(
            "delete jira worklog [%s %s +%ss]",
            worklog['issueKey'], worklog['started'], worklog['timeSpentSeconds']
        )
        try:
            jira.delete_worklog(worklog)
            successful_sync_operations += 1
        except Exception as e:  # pylint: disable=broad-except
            logging.error("failed to delete worklog (%s)", e)

    # add worklogs
    for worklog in worklogs_to_add:
        logging.info(
            "add new jira worklog [%s %s +%ss]",
            worklog['issueKey'], worklog['started'], worklog['timeSpentSeconds']
        )
        try:
            jira.create_worklog(worklog)
            successful_sync_operations += 1
        except Exception as e:  # pylint: disable=broad-except
            logging.error("failed to create worklog (%s)", e)

    # status
    if successful_sync_operations == total_sync_operations:
        logging.info("finished sync successfully")
        sys.exit(EX_OK)
    else:
        logging.error(
            "sync finished with errors. %s/%s sync operations were successful",
            successful_sync_operations, total_sync_operations
        )
        sys.exit(EX_SOFTWARE)


if __name__ == "__main__":
    main()
