from app.main import report_markdown, score_assessment_profile
from app.schemas import AssessmentProfileIn


def test_assessment_profile_prefers_databricks_for_large_streaming_workloads():
    score = score_assessment_profile(
        AssessmentProfileIn(
            current_databricks_usage=True,
            data_volume="large",
            streaming_requirement=True,
            engineering_maturity="high",
            deployment_preference="databricks",
        )
    )

    assert score.recommended_platform == "Databricks"
    assert score.databricks_score > score.fabric_score


def test_report_markdown_includes_metrics_and_recommendations():
    markdown = report_markdown(
        "assessment-test",
        {
            "metrics": {"systems_connected": 2},
            "recommendations": [
                {"title": "Improve lineage", "priority": "High", "description": "Add relationship metadata."}
            ],
            "pain_points": [{"severity": "Medium", "pain_point": "Unknown owners"}],
        },
    )

    assert "# Assessment Report assessment-test" in markdown
    assert "systems_connected: 2" in markdown
    assert "Improve lineage" in markdown
