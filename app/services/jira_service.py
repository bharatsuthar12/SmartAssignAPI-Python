import base64
import httpx

from app.core.config import settings


class JiraService:

    def __init__(self):
        self.base_url = settings.jira_base_url.rstrip("/")

        credentials = (
            f"{settings.jira_username}:{settings.jira_api_token}"
        )

        encoded_credentials = base64.b64encode(
            credentials.encode()
        ).decode()

        self.headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    # ---------------------------------------------------------
    # GET NEW / TO DO ISSUES
    # ---------------------------------------------------------

    async def get_new_issues(
    self,
    project_key: str | None = None
):

     if project_key:
        jql = (
            f'project = "{project_key}" '
            f'AND status = "To Do" '
            f'ORDER BY created ASC'
        )
     else:
        jql = (
            'status = "To Do" '
            'ORDER BY created ASC'
        )

     return await self._get_issues(jql)
    # ---------------------------------------------------------
    # GET EXISTING ISSUES
    # ---------------------------------------------------------

    async def get_existing_issues(
    self,
    project_key: str | None = None
):

     if project_key:
        jql = (
            f'project = "{project_key}" '
            f'AND status != "To Do" '
            f'ORDER BY created DESC'
        )
     else:
        jql = (
            'status != "To Do" '
            'ORDER BY created DESC'
        )

     return await self._get_issues(jql)
    # ---------------------------------------------------------
    # COMMON SEARCH METHOD
    # ---------------------------------------------------------

    async def _get_issues(self, jql: str):

        url = f"{self.base_url}/rest/api/3/search/jql"

        payload = {
            "jql": jql,
            "fields": [
                "summary",
                "description",
                "status",
                "assignee",
                "reporter",
                "created",
                "project",
                "customfield_10240"
            ],
            "maxResults": 50
        }

        async with httpx.AsyncClient(timeout=120) as client:

            response = await client.post(
                url,
                headers=self.headers,
                json=payload
            )

            if response.status_code >= 400:
                print("JIRA STATUS:", response.status_code)
                print("JIRA RESPONSE:", response.text)
                print("JIRA JQL:", jql)

            response.raise_for_status()

            data = response.json()

        issues = data.get("issues", [])

        return [
            self._map_issue(issue)
            for issue in issues
        ]

    # ---------------------------------------------------------
    # MAP JIRA RESPONSE
    # ---------------------------------------------------------

    def _map_issue(self, issue: dict):

        fields = issue.get("fields") or {}

        return {
            "id": issue.get("id", ""),
            "key": issue.get("key", ""),
            "summary": fields.get("summary", ""),
            "description": self._extract_text(
                fields.get("description")
            ),
            "project_key": (
                fields.get("project", {}).get("key", "")
                if fields.get("project")
                else ""
            ),
            "project_name": (
                fields.get("project", {}).get("name", "")
                if fields.get("project")
                else ""
            ),
            "status": (
                fields.get("status", {}).get("name", "")
                if fields.get("status")
                else ""
            ),
            "resolution": self._extract_text(
                fields.get("customfield_10240")
            ),
            "assignee": (
                fields.get("assignee", {}).get("displayName", "Unassigned")
                if fields.get("assignee")
                else "Unassigned"
            ),
            "assignee_account_id": (
                fields.get("assignee", {}).get("accountId", "")
                if fields.get("assignee")
                else ""
            ),
            "reporter": (
                fields.get("reporter", {}).get("displayName", "")
                if fields.get("reporter")
                else ""
            ),
            "created_date": fields.get("created", "")
        }

    # ---------------------------------------------------------
    # EXTRACT DESCRIPTION / RESOLUTION TEXT
    # ---------------------------------------------------------

    @staticmethod
    def _extract_text(value):

        if not value:
            return ""

        if isinstance(value, str):
            return value

        result = []

        def walk(obj):

            if isinstance(obj, dict):

                if "text" in obj:
                    result.append(str(obj["text"]))

                for child in obj.values():
                    walk(child)

            elif isinstance(obj, list):

                for child in obj:
                    walk(child)

        walk(value)

        return " ".join(result)

    # ---------------------------------------------------------
    # ASSIGN SINGLE ISSUE
    # ---------------------------------------------------------

    async def assign_issue(
        self,
        issue_key: str,
        account_id: str
    ):

        url = (
            f"{self.base_url}/rest/api/3/"
            f"issue/{issue_key}/assignee"
        )

        payload = {
            "accountId": account_id
        }

        async with httpx.AsyncClient(timeout=120) as client:

            response = await client.put(
                url,
                headers=self.headers,
                json=payload
            )

            response.raise_for_status()

        return True

    # ---------------------------------------------------------
    # ASSIGN MULTIPLE ISSUES
    # ---------------------------------------------------------

    async def assign_multiple(self, requests: list):

        for request in requests:

            issue_key = request["issueKey"]
            account_id = request["accountId"]

            await self.assign_issue(
                issue_key,
                account_id
            )

            await self.move_to_in_progress(
                issue_key
            )

        return {
            "success": True,
            "totalTickets": len(requests),
            "message": (
                f"{len(requests)} tickets "
                f"assigned successfully."
            )
        }

    # ---------------------------------------------------------
    # MOVE TO IN PROGRESS
    # ---------------------------------------------------------

    async def move_to_in_progress(
        self,
        issue_key: str
    ):

        url = (
            f"{self.base_url}/rest/api/3/"
            f"issue/{issue_key}/transitions"
        )

        async with httpx.AsyncClient(timeout=120) as client:

            response = await client.get(
                url,
                headers=self.headers
            )

            response.raise_for_status()

            data = response.json()

            transitions = data.get(
                "transitions",
                []
            )

            transition = next(
                (
                    item
                    for item in transitions
                    if item.get("name", "").lower()
                    == "in progress"
                ),
                None
            )

            if not transition:
                return False

            payload = {
                "transition": {
                    "id": transition["id"]
                }
            }

            response = await client.post(
                url,
                headers=self.headers,
                json=payload
            )

            response.raise_for_status()

        return True

    # ---------------------------------------------------------
    # GET PROJECTS
    # ---------------------------------------------------------

    async def get_projects(self):

        cache_key = "JiraProjects"

        if hasattr(self, "_project_cache"):
            return self._project_cache

        url = (
            f"{self.base_url}/rest/api/3/"
            f"project/search"
        )

        async with httpx.AsyncClient(timeout=120) as client:

            response = await client.get(
                url,
                headers=self.headers
            )

            response.raise_for_status()

            data = response.json()

        projects = [
            {
                "key": item.get("key", ""),
                "name": item.get("name", "")
            }
            for item in data.get("values", [])
        ]

        self._project_cache = projects

        return projects

    # ---------------------------------------------------------
    # GET ISSUE BY KEY
    # ---------------------------------------------------------

    async def get_issue_by_key(self, issue_key: str):
        url = (
            f"{self.base_url}/rest/api/3/"
            f"issue/{issue_key}"
        )

        params = {
            "fields": (
                "summary,"
                "description,"
                "status,"
                "resolution,"
                "assignee,"
                "reporter,"
                "created,"
                "project"
            )
        }

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(
                url,
                headers=self.headers,
                params=params
            )

            if response.status_code == 404:
                return None

            response.raise_for_status()

            issue = response.json()

        return self._map_issue(issue)

    # ---------------------------------------------------------
    # GET MY ASSIGNED TICKETS
    # ---------------------------------------------------------

    async def get_my_assigned_issues(
        self,
        project_key: str | None = None
    ):

        jql = (
            'assignee = currentUser() '
            'AND status in ("In Progress","In Review")'
        )

        if project_key:
            jql += f' AND project = "{project_key}"'

        jql += " ORDER BY created ASC"

        return await self._get_issues(jql)

    # ---------------------------------------------------------
    # GENERATE REASON
    # ---------------------------------------------------------

    async def generate_reason(
        self,
        new_issue_key: str,
        existing_issue_key: str,
        ai_service
    ):

        new_issue = await self.get_issue_by_key(
            new_issue_key
        )

        existing_issue = await self.get_issue_by_key(
            existing_issue_key
        )

        if not new_issue or not existing_issue:
            return ""

        return await ai_service.generate_reason(
            self.build_text(new_issue),
            self.build_text(existing_issue)
        )

    # ---------------------------------------------------------
    # BUILD AI TEXT
    # ---------------------------------------------------------

    @staticmethod
    def build_text(issue):

        return (
            f"Project: {issue.get('project_name', '')}\n\n"
            f"Summary: {issue.get('summary', '')}\n\n"
            f"Description: {issue.get('description', '')}"
        )

    # ---------------------------------------------------------
    # GET GITHUB BRANCH URL
    # ---------------------------------------------------------

    async def get_github_branch_url(
        self,
        jira_key: str
    ):

        try:

            issue = await self.get_issue_by_key(
                jira_key
            )

            if not issue:
                return ""

            issue_id = issue.get("id")

            if not issue_id:
                return ""

            url = (
                f"{self.base_url}/rest/dev-status/"
                f"latest/issue/detail"
            )

            params = {
                "issueId": issue_id,
                "applicationType":
                    "oAuth-com.github.integration.production",
                "dataType": "branch"
            }

            async with httpx.AsyncClient(
                timeout=120
            ) as client:

                response = await client.get(
                    url,
                    headers=self.headers,
                    params=params
                )

                if not response.is_success:
                    return ""

                data = response.json()

            for detail in data.get("detail", []):

                branches = detail.get(
                    "branches",
                    []
                )

                for branch in branches:

                    branch_url = branch.get("url")

                    if branch_url:
                        return branch_url

            return ""

        except Exception:
            return ""