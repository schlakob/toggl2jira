import json
import sys
import math
import logging
import re
from os import path, EX_OK, EX_DATAERR, EX_SOFTWARE, getcwd
from datetime import date, timedelta
from dateutil import parser
import truststore

from toggl2jira.config import Config
from toggl2jira.jira import Jira, JiraApi
from toggl2jira.toggl import Toggl, TogglApi


def main():
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)
    truststore.inject_into_ssl()
    try:
        config = Config(path.dirname(path.realpath(getcwd())))
    except RuntimeError as e:
        logging.error(f"Could not load config ({e})")
        sys.exit(EX_DATAERR)

    # setup filters
    logging.info(
        f"starting sync with window of {config.sync_window_size} days searching for {config.jira_project_slug}"
    )
    to_date = date.today() + timedelta(days=1)
    from_date = to_date - timedelta(days=config.sync_window_size)

    # creating jira and toggl utilities
    jira_api = JiraApi(config.jira_endpoint, config.jira_access_token)
    jira = Jira(jira_api, config.jira_project_slug)
    toggl_api = TogglApi(config.toggl_endpoint, config.toggl_api_key)
    toggl = Toggl(toggl_api, config.jira_project_slug)

    # get jira user information
    logging.info(f"connecting to jira ({config.jira_endpoint})")
    jira_user = jira.get_user()
    logging.info(f"authenticated as {jira_user['name']}")

    # get jira issues with relevant worklogs
    jira_issues = jira.get_issues_by_worklogs(jira_user, from_date, to_date)
    logging.info(f"found {len(jira_issues)} issues with relevant worklogs")

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
        f"found {len(jira_worklogs)} worklogs, {len(jira_worklogs_filtered)} of which will be synced"
    )
    for jira_worklog in jira_worklogs_filtered:
        logging.debug(
            f"jira worklog [{jira_worklog['issueKey']} {jira_worklog['started']} +{jira_worklog['timeSpentSeconds']}s]"
        )

    # get toggl user information
    logging.info(f"connecting to toggl ({config.toggl_endpoint})")
    toggl_user = toggl.get_user()
    logging.info(f"authenticated as {toggl_user['email']}")

    # get toggl time entries and convert them to worklogs
    toggl_time_entries = toggl.get_time_entries(from_date, to_date)
    toggl_worklogs = list(
        map(lambda te: toggl.convert_time_entry_to_worklog(te), toggl_time_entries)
    )

    # filter synced toggl worklogs
    toggl_worklogs_filtered = list(filter(toggl.worklog_filter, toggl_worklogs))
    logging.info(
        f"found {len(toggl_time_entries)} time entries, {len(toggl_worklogs_filtered)} of which will be synced"
    )
    for worklog in toggl_worklogs_filtered:
        logging.debug(
            f"toggl worklog [{worklog['issueKey']} {worklog['started']} +{worklog['timeSpentSeconds']}s]"
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
        f"{already_synced_count}/{len(toggl_worklogs_filtered)} toggl worklogs are already in sync"
    )
    logging.info(
        f"{len(worklogs_to_add)} jira worklogs to add, {len(worklogs_to_delete)} jira worklogs to delete"
    )

    total_sync_operations = len(worklogs_to_add) + len(worklogs_to_delete)
    successful_sync_operations = 0

    # delete worklogs
    for worklog in worklogs_to_delete:
        logging.info(
            f"delete jira worklog [{worklog['issueKey']} {worklog['started']} +{worklog['timeSpentSeconds']}s]"
        )
        try:
            jira.delete_worklog(worklog)
            successful_sync_operations += 1
        except Exception as e:
            logging.error(f"failed to delete worklog ({e})")

    # add worklogs
    for worklog in worklogs_to_add:
        logging.info(
            f"add new jira worklog [{worklog['issueKey']} {worklog['started']} +{worklog['timeSpentSeconds']}s]"
        )
        try:
            jira.create_worklog(worklog)
            successful_sync_operations += 1
        except Exception as e:
            logging.error(f"failed to create worklog ({e})")

    # status
    if successful_sync_operations == total_sync_operations:
        logging.info("finished sync successfully")
        sys.exit(EX_OK)
    else:
        logging.error(
            f"sync finished with errors. {successful_sync_operations}/{total_sync_operations} sync operations were successful"
        )
        sys.exit(EX_SOFTWARE)


if __name__ == "__main__":
    main()
