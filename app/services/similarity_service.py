import asyncio
from datetime import datetime

from app.services.jira_service import JiraService
from app.services.ai_service import AIService
from app.helpers.cosine_similarity import cosine_similarity
from app.core.config import settings


class SimilarityService:

    def __init__(
        self,
        jira_service: JiraService,
        ai_service: AIService
    ):
        self.jira_service = jira_service
        self.ai_service = ai_service

        # =====================================================
        # CACHE
        # =====================================================

        self._existing_embeddings_cache = None
        self._existing_embeddings_cache_time = None

        self._issue_embedding_cache = {}

        self.cache_minutes = 30

        # =====================================================
        # OLLAMA CONCURRENCY LIMIT
        # =====================================================

        self.embedding_semaphore = asyncio.Semaphore(5)

        # =====================================================
        # REASON CONCURRENCY LIMIT
        # =====================================================

        self.reason_semaphore = asyncio.Semaphore(3)

    # =========================================================
    # MAIN SIMILARITY API
    # =========================================================

    async def find_similar_issues(
        self,
        project_key: str | None = None
    ):

        total_start = datetime.now()

        print("")
        print("==============================================")
        print("SMART ASSIGN - SIMILARITY SEARCH STARTED")
        print("==============================================")

        # =====================================================
        # 1. GET NEW ISSUES
        # =====================================================

        start = datetime.now()

        print("Getting new / To Do issues...")

        new_issues = await self.jira_service.get_new_issues(
            project_key
        )

        print(
            f"New Issues : {len(new_issues)}"
        )

        print(
            f"New issues fetch time : "
            f"{self._elapsed(start):.2f} sec"
        )

        if not new_issues:
            return []

        # =====================================================
        # 2. GET EXISTING ISSUES
        # =====================================================

        start = datetime.now()

        print("Getting existing issues...")

        existing_issues = (
            await self.jira_service.get_existing_issues(
                project_key
            )
        )

        print(
            f"Existing Issues : "
            f"{len(existing_issues)}"
        )

        print(
            f"Existing issues fetch time : "
            f"{self._elapsed(start):.2f} sec"
        )

        if not existing_issues:
            return []

        # =====================================================
        # 3. EXISTING EMBEDDINGS
        # =====================================================

        start = datetime.now()

        print(
            "Preparing existing embeddings..."
        )

        existing_embeddings = (
            await self._get_existing_embeddings(
                existing_issues
            )
        )

        print(
            f"Existing Embeddings : "
            f"{len(existing_embeddings)}"
        )

        print(
            f"Existing embedding stage : "
            f"{self._elapsed(start):.2f} sec"
        )

        # =====================================================
        # 4. NEW ISSUE EMBEDDINGS
        # =====================================================

        start = datetime.now()

        print(
            "Preparing new issue embeddings..."
        )

        new_issue_tasks = [
            self._prepare_new_issue(
                issue
            )
            for issue in new_issues
        ]

        new_issue_data = await asyncio.gather(
            *new_issue_tasks
        )

        print(
            f"New embedding stage : "
            f"{self._elapsed(start):.2f} sec"
        )

        # =====================================================
        # 5. PROCESS NEW ISSUES
        # =====================================================

        results = []

        comparison_start = datetime.now()

        for item in new_issue_data:

            issue_start = datetime.now()

            new_issue = item["issue"]
            new_text = item["text"]
            new_embedding = item["embedding"]
            new_keywords = item["keywords"]

            issue_key = new_issue.get(
                "key",
                ""
            )

            print("")
            print(
                f"Comparing issue : "
                f"{issue_key}"
            )

            if not new_embedding:

                print(
                    f"No embedding found for "
                    f"{issue_key}"
                )

                continue

            # =================================================
            # 6. COSINE SIMILARITY
            # =================================================

            similarity_start = datetime.now()

            matches = []

            for existing in existing_embeddings:

                existing_embedding = (
                    existing.get("embedding")
                )

                if not existing_embedding:
                    continue

                score = (
                    cosine_similarity(
                        new_embedding,
                        existing_embedding
                    )
                    * 100
                )

                if (
                    score
                    >= settings.similarity_threshold
                ):

                    matches.append({
                        "existing": existing,
                        "score": score
                    })

            matches.sort(
                key=lambda x: x["score"],
                reverse=True
            )

            matches = matches[
                :settings.top_results
            ]

            print(
                f"{issue_key} cosine comparison : "
                f"{self._elapsed(similarity_start):.4f} sec"
            )

            print(
                f"{issue_key} matches : "
                f"{len(matches)}"
            )

            if not matches:
                continue

            # =================================================
            # 7. BUILD TOP MATCHES
            # =================================================

            result_start = datetime.now()

            similar_tickets = []

            for match in matches:

                existing_data = (
                    match["existing"]
                )

                existing_issue = (
                    existing_data["issue"]
                )

                similar_tickets.append({

                    "existingData": existing_data,

                    "existingIssue": existing_issue,

                    "score": match["score"],

                    "newText": new_text,

                    "existingText": (
                        self._build_text(
                            existing_issue
                        )
                    ),

                    "newKeywords": new_keywords
                })

            print(
                f"{issue_key} result preparation : "
                f"{self._elapsed(result_start):.4f} sec"
            )

            # =================================================
            # 8. ENRICH TOP MATCHES IN PARALLEL
            # =================================================

            enrichment_start = datetime.now()

            enriched_tickets = await asyncio.gather(
                *[
                    self._build_similar_ticket(
                        item,
                        index
                    )
                    for index, item
                    in enumerate(similar_tickets)
                ]
            )

            print(
                f"{issue_key} enrichment : "
                f"{self._elapsed(enrichment_start):.2f} sec"
            )

            # =================================================
            # 9. BUILD NEW ISSUE RESULT
            # =================================================

            results.append({

                "newJiraKey": new_issue.get(
                    "key",
                    ""
                ),

                "summary": new_issue.get(
                    "summary",
                    ""
                ),

                "description": new_issue.get(
                    "description",
                    ""
                ),

                "projectKey": new_issue.get(
                    "project_key",
                    ""
                ),

                "projectName": new_issue.get(
                    "project_name",
                    ""
                ),

                "status": new_issue.get(
                    "status",
                    ""
                ),

                "assignee": new_issue.get(
                    "assignee",
                    ""
                ),

                "reporter": new_issue.get(
                    "reporter",
                    ""
                ),

                "createdDate": new_issue.get(
                    "created_date",
                    ""
                ),

                "jiraUrl": (
                    f"{settings.jira_base_url.rstrip('/')}"
                    f"/browse/"
                    f"{new_issue.get('key', '')}"
                ),

                "similarTickets": enriched_tickets
            })

            print(
                f"{issue_key} TOTAL : "
                f"{self._elapsed(issue_start):.2f} sec"
            )

        # =====================================================
        # 10. TOTAL TIME
        # =====================================================

        print("")
        print("==============================================")
        print(
            "ALL COMPARISONS TOTAL : "
            f"{self._elapsed(comparison_start):.2f} sec"
        )
        print(
            "TOTAL API TIME : "
            f"{self._elapsed(total_start):.2f} sec"
        )
        print(
            f"Result count : {len(results)}"
        )
        print("==============================================")
        print("")

        return results

    # =========================================================
    # BUILD SIMILAR TICKET
    # =========================================================

    async def _build_similar_ticket(
        self,
        match_data,
        index
    ):

        existing_data = (
            match_data["existingData"]
        )

        existing_issue = (
            match_data["existingIssue"]
        )

        score = match_data["score"]

        new_text = (
            match_data["newText"]
        )

        existing_text = (
            match_data["existingText"]
        )

        new_keywords = (
            match_data["newKeywords"]
        )

        issue_key = existing_issue.get(
            "key",
            ""
        )

        # =====================================================
        # MATCHED KEYWORDS
        # =====================================================

        existing_keywords = (
            existing_data.get(
                "keywords",
                []
            )
        )

        matched_keywords = list(
            set(
                keyword.lower()
                for keyword in new_keywords
            )
            &
            set(
                keyword.lower()
                for keyword in existing_keywords
            )
        )

        # =====================================================
        # GITHUB + REASON IN PARALLEL
        # =====================================================

        github_task = (
            self._get_github_url(
                issue_key
            )
        )

        reason_task = (
            self._get_reason(
                new_text,
                existing_text,
                index
            )
        )

        github_url, reason = await asyncio.gather(
            github_task,
            reason_task
        )

        # =====================================================
        # RESULT
        # =====================================================

        return {

            "jiraKey": issue_key,

            "summary": existing_issue.get(
                "summary",
                ""
            ),

            "description": existing_issue.get(
                "description",
                ""
            ),

            "assignee": existing_issue.get(
                "assignee",
                ""
            ),

            "assigneeAccountId": (
                existing_issue.get(
                    "assignee_account_id",
                    ""
                )
            ),

            "status": existing_issue.get(
                "status",
                ""
            ),

            "resolution": existing_issue.get(
                "resolution",
                ""
            ),

            "similarityScore": round(
                score,
                2
            ),

            "jiraUrl": (
                f"{settings.jira_base_url.rstrip('/')}"
                f"/browse/"
                f"{issue_key}"
            ),

            "reason": reason,

            "projectKey": existing_issue.get(
                "project_key",
                ""
            ),

            "projectName": existing_issue.get(
                "project_name",
                ""
            ),

            "githubUrl": github_url,

            "matchedKeywords": (
                matched_keywords
            )
        }

    # =========================================================
    # GITHUB URL
    # =========================================================

    async def _get_github_url(
        self,
        issue_key
    ):

        try:

            return (
                await self.jira_service
                .get_github_branch_url(
                    issue_key
                )
            )

        except Exception as e:

            print(
                f"GitHub lookup failed "
                f"for {issue_key}: {e}"
            )

            return ""

    # =========================================================
    # AI REASON
    # =========================================================

    async def _get_reason(
        self,
        new_text,
        existing_text,
        index
    ):

        if not settings.generate_reason:

            return ""

        if (
            index
            >= settings.generate_reason_for_top
        ):

            return ""

        try:

            async with self.reason_semaphore:

                return (
                    await self.ai_service
                    .generate_reason(
                        new_text,
                        existing_text
                    )
                )

        except Exception as e:

            print(
                f"Reason generation failed: "
                f"{e}"
            )

            return ""

    # =========================================================
    # EXISTING EMBEDDINGS
    # =========================================================

    async def _get_existing_embeddings(
        self,
        existing_issues
    ):

        now = datetime.now()

        # =====================================================
        # CHECK 30-MINUTE FULL CACHE
        # =====================================================

        if (
            self._existing_embeddings_cache
            is not None
            and
            self._existing_embeddings_cache_time
            is not None
        ):

            elapsed = (
                now
                -
                self._existing_embeddings_cache_time
            ).total_seconds() / 60

            if elapsed < self.cache_minutes:

                print(
                    "Using cached existing embeddings."
                )

                return (
                    self._existing_embeddings_cache
                )

        # =====================================================
        # GENERATE EMBEDDINGS
        # =====================================================

        print(
            f"Generating embeddings for "
            f"{len(existing_issues)} existing issues..."
        )

        start = datetime.now()

        tasks = [
            self._create_embedding_data(
                issue
            )
            for issue in existing_issues
        ]

        embeddings = await asyncio.gather(
            *tasks
        )

        elapsed = (
            datetime.now() - start
        ).total_seconds()

        print(
            f"Existing embedding time : "
            f"{elapsed:.2f} sec"
        )

        # =====================================================
        # REMOVE FAILED EMBEDDINGS
        # =====================================================

        embeddings = [
            item
            for item in embeddings
            if item.get("embedding")
        ]

        # =====================================================
        # CACHE
        # =====================================================

        self._existing_embeddings_cache = (
            embeddings
        )

        self._existing_embeddings_cache_time = (
            datetime.now()
        )

        return embeddings

    # =========================================================
    # CREATE EXISTING EMBEDDING
    # =========================================================

    async def _create_embedding_data(
        self,
        issue
    ):

        issue_key = issue.get(
            "key",
            ""
        )

        text = self._build_text(
            issue
        )

        # =====================================================
        # INDIVIDUAL CACHE
        # =====================================================

        if issue_key:

            cached = (
                self._issue_embedding_cache.get(
                    issue_key
                )
            )

            if cached:

                return cached

        # =====================================================
        # OLLAMA
        # =====================================================

        async with self.embedding_semaphore:

            embedding = (
                await self.ai_service
                .generate_embedding(
                    text
                )
            )

        keywords = (
            self._extract_keywords(
                text
            )
        )

        result = {

            "issue": issue,

            "embedding": embedding,

            "keywords": keywords
        }

        # =====================================================
        # SAVE CACHE
        # =====================================================

        if issue_key:

            self._issue_embedding_cache[
                issue_key
            ] = result

        return result

    # =========================================================
    # PREPARE NEW ISSUE
    # =========================================================

    async def _prepare_new_issue(
        self,
        issue
    ):

        issue_key = issue.get(
            "key",
            ""
        )

        text = self._build_text(
            issue
        )

        # =====================================================
        # CACHE
        # =====================================================

        if issue_key:

            cached = (
                self._issue_embedding_cache.get(
                    issue_key
                )
            )

            if cached:

                return {

                    "issue": issue,

                    "text": text,

                    "embedding": cached[
                        "embedding"
                    ],

                    "keywords": cached[
                        "keywords"
                    ]
                }

        # =====================================================
        # OLLAMA
        # =====================================================

        async with self.embedding_semaphore:

            embedding = (
                await self.ai_service
                .generate_embedding(
                    text
                )
            )

        keywords = (
            self._extract_keywords(
                text
            )
        )

        # =====================================================
        # CACHE
        # =====================================================

        if issue_key:

            self._issue_embedding_cache[
                issue_key
            ] = {

                "issue": issue,

                "embedding": embedding,

                "keywords": keywords
            }

        return {

            "issue": issue,

            "text": text,

            "embedding": embedding,

            "keywords": keywords
        }

    # =========================================================
    # BUILD TEXT
    # =========================================================

    @staticmethod
    def _build_text(
        issue
    ):

        summary = issue.get(
            "summary",
            ""
        )

        description = issue.get(
            "description",
            ""
        )

        return (
            f"{summary}\n\n"
            f"{description}"
        ).strip()

    # =========================================================
    # KEYWORDS
    # =========================================================

    @staticmethod
    def _extract_keywords(
        text
    ):

        stop_words = {

            "the",
            "is",
            "are",
            "was",
            "were",

            "and",
            "or",

            "for",
            "from",

            "this",
            "that",

            "with",

            "have",
            "has",
            "had",

            "not",

            "new",
            "issue",
            "jira",
            "task",
            "report",

            "please",
            "find",
            "attached",
            "below",
            "mentioned",

            "which",
            "other",
            "only",
            "getting",
            "refer"
        }

        words = text.lower().split()

        keywords = []

        for word in words:

            word = word.strip(
                ".,!?;:()[]{}\"'"
            )

            if (
                len(word) > 2
                and word not in stop_words
            ):

                keywords.append(
                    word
                )

        return list(
            dict.fromkeys(
                keywords
            )
        )

    # =========================================================
    # CACHE CLEAR
    # =========================================================

    def clear_cache(
        self
    ):

        self._existing_embeddings_cache = None

        self._existing_embeddings_cache_time = None

        self._issue_embedding_cache.clear()

        print(
            "Similarity cache cleared."
        )

    # =========================================================
    # ELAPSED TIME
    # =========================================================

    @staticmethod
    def _elapsed(
        start_time
    ):

        return (
            datetime.now() - start_time
        ).total_seconds()