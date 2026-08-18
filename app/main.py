from fastapi import FastAPI

from app.services.jira_service import JiraService
from app.services.ai_service import AIService
from app.core.config import settings
from app.services.similarity_service import SimilarityService

app = FastAPI(
    title="SmartAssign API",
    version="1.0.0"
)


jira_service = JiraService()
ai_service = AIService()
similarity_service = SimilarityService(
    jira_service,
    ai_service
)

@app.get("/")
def root():
    return {
        "message": "SmartAssign Python API is running"
    }


@app.get("/api/Jira/test123")
async def test_jira():

    try:
        result = await jira_service.get_new_issues(
            settings.jira_project_key
        )

        return {
            "total": len(result),
            "issues": result
        }

    except Exception as e:
        return {
            "error": str(e)
        }


@app.get("/api/Jira/new-issues")
async def get_new_issues(
    project_key: str | None = None
):

    try:
        result = await jira_service.get_new_issues(
            project_key
        )

        return {
            "total": len(result),
            "issues": result
        }

    except Exception as e:
        return {
            "error": str(e)
        }
        
        
@app.get("/api/Jira/existing-issues")
async def get_existing_issues(
    project_key: str | None = None
):

    try:
        result = await jira_service.get_existing_issues(
            project_key                
        )

        return {
            "total": len(result),
            "issues": result
        }

    except Exception as e:
        return {
            "error": str(e)
        }   
        
        
@app.get("/api/Jira/issue/{issue_key}")
async def get_issue(issue_key: str):

    try:

        result = await jira_service.get_issue_by_key(
            issue_key
        )

        if result is None:
            return {
                "message": "Issue not found"
            }

        return result

    except Exception as e:

        return {
            "error": str(e)
        }             
    
@app.get("/api/AI/test")
async def test_ai():

    try:
        embedding = await ai_service.generate_embedding(
            "Test Jira issue for Smart Assignment"
        )

        return {
            "success": True,
            "embedding_length": len(embedding),
            "first_values": embedding[:5]
        }

    except Exception as e:

        return {
            "success": False,
            "error": str(e)
        }    

        
@app.get("/api/Jira/similarity")
async def get_similarity(
    project_key: str | None = None
):

    try:

        result = await similarity_service.find_similar_issues(
            project_key
        )

        return result

    except Exception as e:

        return {
            "success": False,
            "error": str(e)
        }      