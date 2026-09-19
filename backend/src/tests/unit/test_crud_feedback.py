import pytest
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import MagicMock, AsyncMock


from db import crud
from db.models import ConversionFeedback


@pytest.mark.asyncio
async def test_create_feedback():
    """Test creating a feedback entry."""
    # Mock session
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    # Test data
    job_id = uuid.uuid4()
    feedback_type = "thumbs_up"
    comment = "Great conversion!"
    user_id = "user123"

    # Mock the feedback refresh behavior
    def mock_refresh_side_effect(feedback):
        feedback.id = uuid.uuid4()
        # Also set created_at since it's automatically set by the model
        from datetime import datetime

        feedback.created_at = datetime.now()
        return None

    mock_session.refresh.side_effect = mock_refresh_side_effect

    feedback = await crud.create_enhanced_feedback(
        session=mock_session,
        job_id=job_id,
        feedback_type=feedback_type,
        comment=comment,
        user_id=user_id,
    )

    assert feedback is not None
    assert feedback.id is not None
    assert feedback.job_id == job_id
    assert feedback.feedback_type == feedback_type
    assert feedback.comment == comment
    assert feedback.user_id == "6f36b5ffce979219"
    assert feedback.is_anonymized is True
    assert feedback.created_at is not None

    # Verify session methods were called
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()
    mock_session.refresh.assert_called_once()


@pytest.mark.asyncio
async def test_get_feedback_by_job_id():
    """Test retrieving feedback by job_id."""
    # Mock session
    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = AsyncMock()
    mock_scalars = MagicMock()  # Don't make this async

    job_id = uuid.uuid4()

    # Create mock feedback objects
    feedback1 = MagicMock(spec=ConversionFeedback)
    feedback1.id = uuid.uuid4()
    feedback1.job_id = job_id
    feedback1.feedback_type = "thumbs_up"
    feedback1.comment = "Excellent"
    feedback1.created_at = "2023-01-01T10:00:00"

    feedback2 = MagicMock(spec=ConversionFeedback)
    feedback2.id = uuid.uuid4()
    feedback2.job_id = job_id
    feedback2.feedback_type = "thumbs_down"
    feedback2.comment = "Could be better"
    feedback2.created_at = "2023-01-01T09:00:00"

    mock_scalars.all.return_value = [feedback1, feedback2]
    # Mock the scalars() method to return the mock_scalars object
    mock_result.scalars = MagicMock(return_value=mock_scalars)
    mock_session.execute.return_value = mock_result

    feedbacks = await crud.get_feedback_by_job_id(session=mock_session, job_id=job_id)

    assert feedbacks is not None
    assert len(feedbacks) == 2
    feedback_comments = {f.comment for f in feedbacks}
    assert "Excellent" in feedback_comments
    assert "Could be better" in feedback_comments

    # Verify session.execute was called
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_list_all_feedback():
    """Test listing all feedback entries with pagination."""
    # Mock session
    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = AsyncMock()
    mock_scalars = MagicMock()  # Don't make this async

    # Create mock feedback objects
    fb1 = MagicMock(spec=ConversionFeedback)
    fb1.id = uuid.uuid4()
    fb1.comment = "Job1 Feedback1"
    fb1.created_at = "2023-01-01T09:00:00"

    fb2 = MagicMock(spec=ConversionFeedback)
    fb2.id = uuid.uuid4()
    fb2.comment = "Job2 Feedback1"
    fb2.created_at = "2023-01-01T10:00:00"

    fb3 = MagicMock(spec=ConversionFeedback)
    fb3.id = uuid.uuid4()
    fb3.comment = "Job1 Feedback2"
    fb3.created_at = "2023-01-01T11:00:00"

    fb4 = MagicMock(spec=ConversionFeedback)
    fb4.id = uuid.uuid4()
    fb4.comment = "Job2 Feedback2"
    fb4.created_at = "2023-01-01T12:00:00"

    # Mock returning all feedback in descending order
    all_feedback = [fb4, fb3, fb2, fb1]
    mock_scalars.all.return_value = all_feedback
    # Mock the scalars() method to return the mock_scalars object
    mock_result.scalars = MagicMock(return_value=mock_scalars)
    mock_session.execute.return_value = mock_result

    # Test listing all
    feedbacks_all = await crud.list_all_feedback(session=mock_session, skip=0, limit=10)
    assert len(feedbacks_all) == 4
    assert [f.id for f in feedbacks_all] == [fb4.id, fb3.id, fb2.id, fb1.id]

    # Verify session.execute was called
    mock_session.execute.assert_called_once()

    # Test pagination case
    mock_session.execute.reset_mock()
    mock_scalars.all.return_value = [fb3, fb2]  # Skip 1, limit 2
    mock_result.scalars = MagicMock(return_value=mock_scalars)
    feedbacks_paginated = await crud.list_all_feedback(session=mock_session, skip=1, limit=2)
    assert len(feedbacks_paginated) == 2
    assert [f.id for f in feedbacks_paginated] == [fb3.id, fb2.id]

    # Test empty case
    mock_session.execute.reset_mock()
    mock_scalars.all.return_value = []
    mock_result.scalars = MagicMock(return_value=mock_scalars)
    feedbacks_empty = await crud.list_all_feedback(session=mock_session, skip=4, limit=10)
    assert len(feedbacks_empty) == 0
