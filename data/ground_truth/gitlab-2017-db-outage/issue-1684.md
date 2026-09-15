<!--
Source: https://gitlab.com/api/v4/projects/gitlab-com%2Finfrastructure/issues/1684
        (GitLab REST API v4; the project was later renamed/moved — the issue
        now resolves under
        https://gitlab.com/gitlab-com/gl-infra/production-engineering/-/work_items/1684)
        Web page: https://gitlab.com/gitlab-com/infrastructure/-/issues/1684
Fetched: 2026-09-15 via mcp__ddg-search__fetch_content (JSON + rendered page;
the plain fetch tool refuses gitlab.com API URLs per robots.txt).
Verbatim field values below. The 6 discussion notes could not be retrieved:
the v4 notes endpoint returned 401 Unauthorized for unauthenticated clients
at fetch time; only the description (which carries the per-issue status
checklist) is used in the ground truth.
-->

# GitLab issue #1684 — "[meta] Listing all issues related to Jan 31st outage to track their progress"

## API record (verbatim key fields)

```json
{
  "iid": 1684,
  "title": "[meta] Listing all issues related to Jan 31st outage to track their progress",
  "state": "closed",
  "created_at": "2017-04-28T01:22:26.859Z",
  "updated_at": "2018-03-05T20:42:33.841Z",
  "closed_at": "2018-01-22T08:55:11.530Z",
  "author": {"username": "ernstvn-gitlab", "name": "Ernst van Nierop"},
  "assignee": "[omitted in this copy — unused metadata; see the source URL for the full record]",
  "labels": ["meta"],
  "user_notes_count": 6,
  "upvotes": 3,
  "web_url": "https://gitlab.com/gitlab-com/gl-infra/production-engineering/-/work_items/1684"
}
```

## Description (verbatim)

> Tracking _all_ the issues that were spawned from or referenced in the Jan
> 31st outage blog post-mortem:
> https://about.gitlab.com/2017/02/10/postmortem-of-database-outage-of-january-31/
>
> Mostly doing this for my own benefit, but feel free to update or recommend
> a better way of tracking this.
>
> Issues and their updates:
>
> - :large_orange_diamond: Removal of users by spam should not hard delete
>   https://gitlab.com/gitlab-org/gitlab-ce/issues/27581
> - :white_check_mark: Update PS1 across all hosts to more clearly
>   differentiate between hosts and environments (#1094)
> - :white_check_mark: Prometheus monitoring for backups (#1095)
>   - Now went to zero-loss continuous streaming to S3 bucket and Azure blob
>     using WAL-E (#1152)
>   - WAL-E implemented per #1152, but no monitoring available yet so #1095
>     remains open.
> - :white_check_mark: Set PostgreSQL's max_connections to a sane value (#1096)
> - :white_check_mark: Investigate Point in time recovery & continuous
>   archiving for PostgreSQL (#1097)
>   - Was closed based on comment
>     https://gitlab.com/gitlab-com/infrastructure/issues/494#note_23009747
>     (using Wal-E instead of PITR).
> - :white_check_mark: Hourly LVM snapshots of the production databases (#1098)
> - :white_check_mark: Azure disk snapshots of production databases (#1099)
>   - Superseded by "Fix Azure snapshots" (#1606)
>   - #1606 now dependent on "Convert GitLab ARM Hosts to "Managed Disk"" (#1649)
> - :white_check_mark: Move staging to the ARM environment (#1100)
> - :white_check_mark: Recover production replica(s) (#1101)
> - :large_orange_diamond: Automated testing of recovering PostgreSQL database
>   backups (#1102)
>   - Superseded by Automate restoring a database with Wal-E (#1265)
> - :white_check_mark: Improve PostgreSQL replication documentation/runbooks (#1103)
> - :white_check_mark: Investigate pgbarman for creating PostgreSQL backups (#1105)
>   - Closed by decision to use Wal-E
>     (https://gitlab.com/gitlab-com/infrastructure/issues/494#note_23009747)
> - :white_check_mark: Investigate using WAL-E as a means of Database Backup
>   and Realtime Replication (#494)
> - :white_check_mark: Build Streaming Database Backup (#1152)
> - :white_check_mark: Assign an owner for data durability (#1163)
> - :white_check_mark: Merge Request: Bundle pgpool-II 3.6.1
>   (https://gitlab.com/gitlab-org/omnibus-gitlab/merge_requests/1251)
>   - Closed in favor of "Adding pgbouncer as EE specific dependency"
>     (https://gitlab.com/gitlab-org/omnibus-gitlab/merge_requests/1345)
> - :white_check_mark: Connection pooling/load balancing for PostgreSQL (#259)
>   - Superseded by setting up pgbouncer (#1440)
> - :large_orange_diamond: Tool for executing and reverting Rails migrations
>   on staging (#811)
>   - Lower priority than other tasks, and potential to be superseded by #1504.
> - :large_orange_diamond: Disaster recovery for everything that is not the
>   database (#1161)
>   - This is a meta issue itself, with various linked issues that may take
>     quite a while still.

(:white_check_mark: = done at the time the description was last edited;
:large_orange_diamond: = still open; the rendered page shows "Edited Jul 18,
2017 by Ernst van Nierop".)
