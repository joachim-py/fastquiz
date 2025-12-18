import json 
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, case
from models import models
from schema import schemas
from config.database import get_db
from config.auth import get_current_active_student, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from config.auth import get_current_admin_user

exam_router = APIRouter()
admin_router = APIRouter(prefix="/admin")


# ============= AUTH ============
# Login route
@exam_router.post("/auth/exam-login", response_model=schemas.ExamAuthToken)
async def exam_login(login_data: schemas.ExamLoginInput, db: Session = Depends(get_db)):
    student_model = db.query(models.Student).filter(models.Student.reg_number == login_data.reg_number).first()
    
    if not student_model:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Registration Number or Exam Password."
        )
    current_date = date.today()
    current_time = datetime.now().time()

    schedule_model = db.query(models.ExamSchedule).filter(
        models.ExamSchedule.exam_password == login_data.exam_password,
        models.ExamSchedule.exam_date == current_date,
        models.ExamSchedule.class_id == student_model.class_id
    ).first()

    if not schedule_model:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Exam Password, or the exam is not scheduled for your class today."
        )

    start_dt = datetime.combine(current_date, schedule_model.start_time)
    end_dt = start_dt + timedelta(minutes=schedule_model.duration_minutes)
    now_dt = datetime.combine(current_date, datetime.now().time())

    if now_dt < start_dt:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This exam has not yet started. Scheduled start time is {schedule_model.start_time.strftime('%I:%M %p')}."
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    token_data = {
        "sub": student_model.reg_number,
        "student_id": student_model.id,
        "class_id": student_model.class_id,
        "schedule_id": schedule_model.id
    }
    
    access_token = create_access_token(data=token_data, expires_delta=access_token_expires)

    return schemas.ExamAuthToken(access_token=access_token)


# ============= EXAM SESSION ============
# Start exam session
@exam_router.post("/exam/start/{schedule_id}", response_model=schemas.ExamStartResponse)
async def start_exam_session(schedule_id: int, current_user_data: schemas.TokenData = Depends(get_current_active_student), db: Session = Depends(get_db)):
    
    student_id = current_user_data.student_id
    current_class_id = current_user_data.class_id
    
    exam_schedule = db.query(models.ExamSchedule).options(
        joinedload(models.ExamSchedule.subject),
        joinedload(models.ExamSchedule.question_groups)
        .joinedload(models.QuestionGroup.questions)
        .joinedload(models.Question.options)
    ).filter(
        models.ExamSchedule.id == schedule_id
    ).first()
    
    if not exam_schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam Schedule not found.")
    
    if exam_schedule.class_id != current_class_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. This exam is not scheduled for your class.")

    existing_attempt = db.query(models.ScheduledAttempt).filter(
        models.ScheduledAttempt.student_id == student_id,
        models.ScheduledAttempt.schedule_id == schedule_id
    ).first()
    
    if existing_attempt:
        if existing_attempt.end_time is None:
            new_attempt = existing_attempt 
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This exam has already been completed and submitted.")
    else:
        new_attempt = models.ScheduledAttempt(
            student_id=student_id,
            schedule_id=schedule_id,
            start_time=datetime.now(),
            score=0
        )
        db.add(new_attempt)
        db.commit()
        db.refresh(new_attempt)

    today = date.today()
    now_dt = datetime.combine(today, datetime.now().time())
    
    schedule_start_dt = datetime.combine(exam_schedule.exam_date, exam_schedule.start_time)
    schedule_end_dt = schedule_start_dt + timedelta(minutes=exam_schedule.duration_minutes)

    if exam_schedule.exam_date != today:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This exam is not scheduled for today.")

    if not (schedule_start_dt <= now_dt <= schedule_end_dt):
        if now_dt < schedule_start_dt:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="The exam has not yet started.")
        else:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="The exam period has elapsed. It is now closed.")

    total_questions = sum(
        len(group.questions) for group in exam_schedule.question_groups
    )
    
    if total_questions == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No questions found for this exam schedule.")

    response_data = {
        "attempt_id": new_attempt.id,
        "schedule_id": schedule_id,
        "subject_name": exam_schedule.subject.name, 
        "duration_minutes": exam_schedule.duration_minutes,
        "question_groups": exam_schedule.question_groups,
    }

    return schemas.ExamStartResponse.model_validate(response_data)

# Submit answer route
@exam_router.post("/exam/attempt/{attempt_id}/answers", response_model=schemas.AnswerValidationResponse)
async def submit_answer(attempt_id: int, submission: schemas.AnswerInput, current_user_data: schemas.TokenData = Depends(get_current_active_student), db: Session = Depends(get_db)):
    student_id = current_user_data.student_id

    attempt_model = db.query(models.ScheduledAttempt).filter(
        models.ScheduledAttempt.id == attempt_id,
        models.ScheduledAttempt.student_id == student_id
    ).first()
    
    if not attempt_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam Attempt not found or access denied.")
    
    schedule_model = attempt_model.schedule
    schedule_model = attempt_model.schedule
    
    if attempt_model.end_time:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This exam has already concluded and cannot accept more answers.")
    
    scheduled_end_dt = attempt_model.start_time + timedelta(minutes=schedule_model.duration_minutes)
    now_utc = datetime.now()
    
    if now_utc > scheduled_end_dt:
        attempt_model.end_time = now_utc
        db.commit()
        
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Time limit reached. Exam has been auto-submitted. Answer not recorded.")

    question_model = db.query(models.Question).filter(
        models.Question.id == submission.question_id,
        models.Question.schedule_id == schedule_model.id
    ).first()
    
    if not question_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found or does not belong to this exam.")

    is_correct = (submission.selected_option_id == question_model.correct_option_id)

    existing_answer = db.query(models.UserAnswer).filter(
        models.UserAnswer.attempt_id == attempt_id,
        models.UserAnswer.question_id == submission.question_id
    ).first()

    if existing_answer:
        if existing_answer.is_correct:
            attempt_model.score -= 1
            
        existing_answer.selected_option_id = submission.selected_option_id
        existing_answer.is_correct = is_correct
        existing_answer.answered_at = now_utc
        
        db.add(existing_answer)
        
    else:
        new_user_answer = models.UserAnswer(
            attempt_id=attempt_id,
            question_id=submission.question_id,
            selected_option_id=submission.selected_option_id,
            is_correct=is_correct,
            correct_option_id=question_model.correct_option_id,
            answered_at=now_utc
        )
        db.add(new_user_answer)
    
    if is_correct:
        attempt_model.score += 1

    db.commit()
    
    return schemas.AnswerValidationResponse(
        is_correct=is_correct,
        correct_option_id=question_model.correct_option_id,
        user_selected_option_id=submission.selected_option_id,
    )

# Finish Exam Session
@exam_router.post("/exam/attempt/{attempt_id}/finish", response_model=schemas.ExamResult)
async def finish_exam_session(attempt_id: int, current_user_data: schemas.TokenData = Depends(get_current_active_student), db: Session = Depends(get_db)):
    student_id = current_user_data.student_id
    now_utc = datetime.now()

    attempt_model = db.query(models.ScheduledAttempt).filter(
        models.ScheduledAttempt.id == attempt_id,
        models.ScheduledAttempt.student_id == student_id
    ).first()
    
    if not attempt_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam Attempt not found or access denied.")
        
    if attempt_model.end_time:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This exam has already been finalized.")

    schedule_model = attempt_model.schedule
    subject_model = schedule_model.subject
    elapsed_time_seconds = (now_utc - attempt_model.start_time).total_seconds()
    time_limit_seconds = schedule_model.duration_minutes * 60
    
    is_time_up = (elapsed_time_seconds >= time_limit_seconds)

    if is_time_up:
        elapsed_time_seconds = time_limit_seconds
        
    attempt_model.end_time = now_utc
    
    total_questions = db.query(models.Question).filter(
        models.Question.schedule_id == schedule_model.id
    ).count()

    subject_score_query = (
        db.query(
            models.Subject.id.label('subject_id'),
            models.Subject.name.label('subject_name'),
            func.sum(case((models.UserAnswer.is_correct == True, 1), else_=0)).label('correct_answers'),
            func.count(models.UserAnswer.id).label('total_answered_questions')
        )
        .join(models.Question, models.UserAnswer.question_id == models.Question.id)
        .join(models.ExamSchedule, models.Question.schedule_id == models.ExamSchedule.id)
        .join(models.Subject, models.ExamSchedule.subject_id == models.Subject.id)
        .filter(models.UserAnswer.attempt_id == attempt_id)
        .group_by(models.Subject.id, models.Subject.name)
        .first()
    )

    if subject_score_query is None:
        subject_report = schemas.SubjectScoreDetail(
            subject_id=subject_model.id,
            subject_name=subject_model.name,
            correct_answers=0,
            total_answered_questions=0
        )
    else:
        subject_report = schemas.SubjectScoreDetail(
            subject_id=subject_score_query.subject_id,
            subject_name=subject_score_query.subject_name,
            correct_answers=subject_score_query.correct_answers,
            total_answered_questions=subject_score_query.total_answered_questions
        )
        
    subject_breakdown_json = subject_report.model_dump_json()

    new_report = models.FinalReport(
        attempt_id=attempt_id,
        subject_scores_json=subject_breakdown_json,
        final_score=attempt_model.score,
        time_taken_seconds=int(elapsed_time_seconds),
    )
    db.add(new_report)
    db.commit()
    
    final_score = attempt_model.score
    
    return schemas.ExamResult(
        attempt_id=attempt_id,
        final_score=final_score,
        total_questions=total_questions,
        percentage_score=(final_score / total_questions) * 100 if total_questions > 0 else 0.0,
        time_taken_seconds=int(elapsed_time_seconds),
        is_time_up_submission=is_time_up,
        subject_report=subject_report
    )

# Get Exam Report
@exam_router.get("/exam/attempt/{attempt_id}/report", response_model=schemas.ExamResult)
async def get_exam_report(attempt_id: int, current_user_data: schemas.TokenData = Depends(get_current_active_student), db: Session = Depends(get_db)):
    student_id = current_user_data.student_id

    report_model = db.query(models.FinalReport).filter(
        models.FinalReport.attempt_id == attempt_id,
        models.FinalReport.attempt.has(models.ScheduledAttempt.student_id == student_id)
    ).first()
    
    if not report_model:
        raise HTTPException(
            status_code=404, 
            detail="Exam Report not found. The exam may not be completed."
        )

    attempt_model = report_model.attempt
    schedule_model = attempt_model.schedule
    subject_model = schedule_model.subject
    
    if attempt_model.end_time is None:
         raise HTTPException(status_code=400, detail="The exam is not yet finished.")

    subject_breakdown_data = json.loads(report_model.subject_scores_json)
    subject_report = schemas.SubjectScoreDetail(**subject_breakdown_data)
    
    total_questions = db.query(models.Question).filter(
        models.Question.schedule_id == schedule_model.id
    ).count()

    time_limit_seconds = schedule_model.duration_minutes * 60
    is_time_up_submission = (report_model.time_taken_seconds >= time_limit_seconds)
    final_score = report_model.final_score
    
    return schemas.ExamResult(
        attempt_id=attempt_id,
        final_score=final_score,
        total_questions=total_questions,
        percentage_score=(final_score / total_questions) * 100 if total_questions > 0 else 0.0,
        time_taken_seconds=report_model.time_taken_seconds,
        is_time_up_submission=is_time_up_submission,
        subject_report=subject_report
    )


# ============= CLASS ============
# Create Class
@admin_router.post("/classes", response_model=schemas.ClassDisplay)
async def create_class(class_data: schemas.Class, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    existing_class = db.query(models.Class).filter(models.Class.name == class_data.name).first()
    
    if existing_class:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Class name already exists.")
    
    class_model = models.Class(name=class_data.name)

    db.add(class_model)
    db.commit()
    db.refresh(class_model)

    return class_model

# Get all classes
@admin_router.get("/classes", response_model=List[schemas.ClassDisplay])
async def read_classes(admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    classes = db.query(models.Class).all()
    return classes

# Update class
@admin_router.put("/classes/{class_id}", response_model=schemas.ClassDisplay)
async def update_class(class_id: int, class_data: schemas.Class, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    class_model = db.query(models.Class).filter(models.Class.id == class_id).first()
    
    if not class_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found.")
    
    new_name = class_data.name
    
    if new_name != class_model.name:
        existing_class = db.query(models.Class).filter(models.Class.name == new_name).first()
        
        if existing_class:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"The class name '{new_name}' already exists. Class names must be unique."
            )
            
    class_model.name = new_name
    
    db.add(class_model)
    db.commit()
    db.refresh(class_model)
    
    return class_model

# Delete class
@admin_router.delete("/classes/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_class(class_id: int, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    class_model = db.query(models.Class).filter(models.Class.id == class_id).first()
    
    if not class_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found.")
    
    student_count = db.query(models.Student).filter(models.Student.class_id == class_id).count()
    schedule_count = db.query(models.ExamSchedule).filter(models.ExamSchedule.class_id == class_id).count()
    
    if student_count > 0 or schedule_count > 0:
        detail_msg = f"Cannot delete Class ID {class_id}. Linked records exist: {student_count} students, {schedule_count} schedules."
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail_msg)

    db.delete(class_model)
    db.commit()
    return


# ============= SCHEDULE ============
# Create Schedule
@admin_router.post("/schedules", response_model=schemas.ExamScheduleDisplay)
async def create_schedule(schedule_data: schemas.ExamSchedule, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Creates a new exam slot, locking a subject to a class, date, and password."""
    
    if not db.query(models.Subject).get(schedule_data.subject_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    
    if not db.query(models.Class).get(schedule_data.class_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found.")

    schedule_model = models.ExamSchedule(**schedule_data.model_dump())
    db.add(schedule_model)
    
    try:
        db.commit()
        db.refresh(schedule_model)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Database error during schedule creation: {e}")
    
    data = schedule_model.__dict__.copy()
    data["subject_name"] = schedule_model.subject.name
    return schemas.ExamScheduleDisplay.model_validate(data)

# Get all schedules
@admin_router.get("/schedules", response_model=List[schemas.ExamScheduleDisplay])
async def read_schedules(class_id: Optional[int] = None, exam_date: Optional[date] = None, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Retrieves all exam schedules, optionally filtered by class or date."""
    shedule_model = db.query(models.ExamSchedule).options(joinedload(models.ExamSchedule.subject), joinedload(models.ExamSchedule.exam_class))
    
    if class_id is not None:
        shedule_model = shedule_model.filter(models.ExamSchedule.class_id == class_id)
    
    if exam_date is not None:
        shedule_model = shedule_model.filter(models.ExamSchedule.exam_date == exam_date)
        
    schedules = shedule_model.all()
    
    return [
        schemas.ExamScheduleDisplay.model_validate(
            {**s.__dict__, "subject_name": s.subject.name}
        )
        for s in schedules
    ]

# Update Schedule
@admin_router.put("/schedules/{schedule_id}", response_model=schemas.ExamScheduleDisplay)
async def update_schedule(schedule_id: int, schedule_data: schemas.ExamSchedule, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Updates an existing exam schedule."""
    
    schedule_model = db.query(models.ExamSchedule).filter(models.ExamSchedule.id == schedule_id).first()
    
    if not schedule_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Exam Schedule with ID {schedule_id} not found.")

    update_data = schedule_data.model_dump(exclude_unset=True)
    
    if 'subject_id' in update_data and not db.query(models.Subject).get(update_data['subject_id']):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="New subject ID not found.")
    
    if 'class_id' in update_data and not db.query(models.Class).get(update_data['class_id']):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="New class ID not found.")

    for key, value in update_data.items():
        setattr(schedule_model, key, value)

    db.add(schedule_model)
    db.commit()
    db.refresh(schedule_model)
    
    schedule_updated = db.query(models.ExamSchedule).options(joinedload(models.ExamSchedule.subject)).filter(models.ExamSchedule.id == schedule_id).first()
    
    data = schedule_model.__dict__.copy()
    data["subject_name"] = schedule_updated.subject.name
    
    return schemas.ExamScheduleDisplay.model_validate(data)

# Delete Schedule
@admin_router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(schedule_id: int, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Deletes an exam schedule only if no student has attempted it and no questions are linked."""
    
    schedule_model = db.query(models.ExamSchedule).filter(models.ExamSchedule.id == schedule_id).first()
    
    if not schedule_model:
        raise HTTPException(status_code=status.status.HTTP_404_NOT_FOUND, detail=f"Exam Schedule with ID {schedule_id} not found.")

    attempt_count = db.query(models.ScheduledAttempt).filter(models.ScheduledAttempt.schedule_id == schedule_id).count()

    if attempt_count > 0:
        raise HTTPException(
            status_code=status.status.HTTP_400_BAD_REQUEST, 
            detail=f"Cannot delete schedule. {attempt_count} student attempts are already recorded for this exam."
        )

    question_count = db.query(models.Question).filter(models.Question.schedule_id == schedule_id).count()

    if question_count > 0:
         raise HTTPException(
            status_code=status.status.HTTP_400_BAD_REQUEST, 
            detail=f"Cannot delete schedule. {question_count} questions are linked. Delete questions first."
        )
         
    db.delete(schedule_model) 
    db.commit()
    
    return

# Dashboard schedule route
@exam_router.get("/dashboard/schedule", response_model=schemas.ExamScheduleDashboard)
async def get_student_exam_schedule(token_data: schemas.TokenData = Depends(get_current_active_student), db: Session = Depends(get_db)):
    
    schedule_id = token_data.schedule_id
    
    schedule_model = db.query(models.ExamSchedule).options(
        joinedload(models.ExamSchedule.subject),
        joinedload(models.ExamSchedule.question_groups).joinedload(models.QuestionGroup.questions)
    ).filter(
        models.ExamSchedule.id == schedule_id,
        models.ExamSchedule.class_id == token_data.class_id
    ).first()
    
    if not schedule_model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Scheduled exam not found or not assigned to your class."
        )

    number_of_groups = len(schedule_model.question_groups)
    total_questions = sum(
        len(group.questions) for group in schedule_model.question_groups
    )
    
    data = schedule_model.__dict__.copy()
    data["subject_name"] = schedule_model.subject.name
    data["number_of_groups"] = number_of_groups
    data["total_questions"] = total_questions
    
    return schemas.ExamScheduleDashboard.model_validate(data)


# ============= STUDENT ============
# Create Student
@admin_router.post("/students", response_model=schemas.StudentDisplay)
async def create_student(student_data: schemas.Student, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Enrolls a new student with a unique registration number and class."""
    
    if not db.query(models.Class).get(student_data.class_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Class ID {student_data.class_id} not found.")

    existing_student = db.query(models.Student).filter(models.Student.reg_number == student_data.reg_number).first()
    
    if existing_student:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Registration number already exists.")

    student_model = models.Student(**student_data.model_dump())
    
    db.add(student_model)
    db.commit()
    db.refresh(student_model)
    
    return student_model

# Get All Students
@admin_router.get("/students", response_model=List[schemas.StudentDisplay])
async def read_students(class_id: Optional[int] = None, limit: int = 100, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Retrieves all students, filterable by class ID."""
    student_model = db.query(models.Student)
    
    if class_id is not None:
        student_model = student_model.filter(models.Student.class_id == class_id)
        
    students = student_model.limit(limit).all()
    return students

# Update Student
@admin_router.put("/students/{student_id}", response_model=schemas.StudentDisplay)
async def update_student(student_id: int, student_data: schemas.Student, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Updates an existing student's details."""
    student_model = db.query(models.Student).filter(models.Student.id == student_id).first()
    
    if not student_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Student ID {student_id} not found.")

    update_data = student_data.model_dump(exclude_unset=True)
    
    if 'class_id' in update_data and not db.query(models.Class).get(update_data['class_id']):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="New Class ID not found.")

    if 'reg_number' in update_data:
        existing_student = db.query(models.Student).filter(models.Student.reg_number == update_data['reg_number'], models.Student.id != student_id).first()
        
        if existing_student:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Registration number is already in use by another student.")

    for key, value in update_data.items():
        setattr(student_model, key, value)

    db.add(student_model)
    db.commit()
    db.refresh(student_model)
    
    return student_model

# Delete Student
@admin_router.delete("/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_student(student_id: int, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Deletes a student and all associated exam attempt records."""
    student_model = db.query(models.Student).filter(models.Student.id == student_id).first()
    
    if not student_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Student ID {student_id} not found.")

    active_attempts = db.query(models.ScheduledAttempt).filter(models.ScheduledAttempt.student_id == student_id, models.ScheduledAttempt.end_time.is_(None)).count()

    if active_attempts > 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete student with an active, unfinished exam attempt.")

    db.delete(student_model)
    db.commit()
    
    return


# ============= SUBJECT ============
# Create Subject
@admin_router.post("/subjects", response_model=schemas.SubjectDisplay)
async def create_subject(subject_data: schemas.Subject, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Creates a new exam subject."""
    existing_subject = db.query(models.Subject).filter(models.Subject.name == subject_data.name).first()
    
    if existing_subject:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Subject name already exists.")
    
    subject_model = models.Subject(name=subject_data.name)
    
    db.add(subject_model)
    db.commit()
    db.refresh(subject_model)
    
    return subject_model

# Get all subjects
@admin_router.get("/subjects", response_model=List[schemas.SubjectDisplay])
async def read_all_subjects(admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Retrieves all subjects."""
    
    subjects =  db.query(models.Subject).all()
    
    return subjects

# Get a Subject
@admin_router.get("/subjects/{subject_id}", response_model=schemas.SubjectDisplay)
async def read_subject(subject_id: int, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Retrieves a single subject."""
    
    subject_model = db.query(models.Subject).filter(models.Subject.id == subject_id).first()
    
    if not subject_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    
    return subject_model

# Update Subject
@admin_router.put("/subjects/{subject_id}", response_model=schemas.SubjectDisplay)
async def update_subject(subject_id: int, subject_data: schemas.Subject, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Updates the name of an existing subject."""
    
    subject_model = db.query(models.Subject).filter(models.Subject.id == subject_id).first()
    
    if not subject_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    
    new_name = subject_data.name
    
    if new_name != subject_model.name:
        existing_subject = db.query(models.Subject).filter(models.Subject.name == new_name).first()
        
        if existing_subject:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"The subject name '{new_name}' already exists. Subject names must be unique."
            )
    
    subject_model.name = new_name

    db.add(subject_model)
    db.commit()
    db.refresh(subject_model)
    
    return subject_model

# Delete Subject
@admin_router.delete("/subjects/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subject(subject_id: int, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Deletes a subject. Requires checking for linked content."""
    
    subject_model = db.query(models.Subject).filter(models.Subject.id == subject_id).first()
    
    if not subject_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")

    question_count = db.query(models.Question).join(models.ExamSchedule).filter(models.ExamSchedule.subject_id == subject_id).count()
    if question_count > 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot delete subject. {question_count} questions are still linked to it.")

    schedule_count = db.query(models.ExamSchedule).filter(models.ExamSchedule.subject_id == subject_id).count()
    if schedule_count > 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot delete subject. {schedule_count} exam schedules are linked to it.")

    db.delete(subject_model)
    db.commit()
    
    return


# ============= QUESTION ============
# Create Question for a specific scheduled exam
@admin_router.post("/groups/{group_id}/questions", response_model=schemas.QuestionStudentDisplay)
async def create_question_and_options(group_id: int, question_data: schemas.Question, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """
    Creates a new question and its options, linking it to a specific Question Group.
    """
    group_model = db.query(models.QuestionGroup).get(group_id)
    if not group_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question Group not found.")

    correct_options = [opt for opt in question_data.options if opt.is_correct]
    if len(correct_options) != 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exactly one option must be marked as correct.")
        
    if not question_data.options:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A question must have at least one option.")

    question_model = models.Question(
        group_id=group_id,
        question_text=question_data.question_text,
    )
    db.add(question_model)
    db.flush() 

    correct_option_id = None
    
    for option_data in question_data.options:
        option_model = models.Option(option_text=option_data.option_text, question_id=question_model.id)
        db.add(option_model)
        db.flush() 
        
        if option_data.is_correct:
            correct_option_id = option_model.id
            
    question_model.correct_option_id = correct_option_id
    
    db.commit()
    db.refresh(question_model)
    
    question_model_complete = db.query(models.Question).options(joinedload(models.Question.options)).filter(models.Question.id == question_model.id).first()
    
    return question_model_complete

# Read all Questions for a specific question group
@admin_router.get("/groups/{group_id}/questions", response_model=list[schemas.QuestionStudentDisplay])
async def read_questions(group_id: int, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    
    question_model = db.query(models.Question).options(joinedload(models.Question.options)
            ).filter(models.Question.group_id == group_id).all()
    
    if not question_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found for this group.")
        
    return question_model

# Read Question for a specific scheduled exam
@admin_router.get("/groups/{group_id}/questions/{question_id}", response_model=schemas.QuestionStudentDisplay)
async def read_question(group_id: int, question_id: int, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Retrieves a single question and its options for a specific group."""
    
    question_model = db.query(models.Question).options(joinedload(models.Question.options)
            ).filter(models.Question.id == question_id, models.Question.group_id == group_id).first()
    
    if not question_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found for this group.")
        
    return question_model

# Update Question for a specific scheduled exam
@admin_router.put("/groups/{group_id}/questions/{question_id}", response_model=schemas.QuestionStudentDisplay)
async def update_question(group_id: int, question_id: int, question_data: schemas.Question, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Updates a question's text, number, and completely replaces all its options within a group."""
    
    question_model = db.query(models.Question).filter(models.Question.id == question_id, models.Question.group_id == group_id).first()
    
    if not question_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found for this group.")

    correct_options = [opt for opt in question_data.options if opt.is_correct]
    if len(correct_options) != 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exactly one option must be marked as correct.")

    question_model.question_text = question_data.question_text

    db.query(models.Option).filter(models.Option.question_id == question_id).delete(synchronize_session=False)
    db.flush()

    new_correct_option_id = None
    
    for option_data in question_data.options:
        option_model = models.Option(option_text=option_data.option_text, question_id=question_model.id)
        db.add(option_model)
        db.flush()
        
        if option_data.is_correct:
            new_correct_option_id = option_model.id
            
    question_model.correct_option_id = new_correct_option_id

    db.commit()
    
    question_model_updated = db.query(models.Question).options(joinedload(models.Question.options)).filter(models.Question.id == question_id).first()
    
    return question_model_updated

# Delete Question for a specific scheduled exam
@admin_router.delete("/groups/{group_id}/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(group_id: int, question_id: int, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Deletes a question (and its options via cascade) after checking for attempts."""
    
    answer_count = db.query(models.UserAnswer).filter(models.UserAnswer.question_id == question_id).count()
    
    if answer_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Cannot delete question. It has already been answered in recorded exams."
        )

    question_model = db.query(models.Question).filter(models.Question.id == question_id, models.Question.group_id == group_id).first()
    
    if not question_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found for this group.")

    question_model.correct_option_id = None
    db.flush() 

    db.delete(question_model)
    db.commit()
    
    return


# ============= QUESTION GROUP ============
# Create Question Group
@admin_router.post("/schedules/{schedule_id}/groups", response_model=schemas.QuestionGroupDisplay)
async def create_question_group(schedule_id: int, group_data: schemas.QuestionGroup, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """
    Creates a new question group (section/instruction block) for a specific exam schedule.
    """
    schedule_model = db.query(models.ExamSchedule).get(schedule_id)
    if not schedule_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam Schedule not found.")

    existing_group = db.query(models.QuestionGroup).filter(
        models.QuestionGroup.schedule_id == schedule_id,
        models.QuestionGroup.display_order == group_data.display_order
    ).first()
    
    if existing_group:
         raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, 
            detail=f"Display order {group_data.display_order} already used in this schedule. Please choose a unique order number."
        )

    group_model = models.QuestionGroup(
        schedule_id=schedule_id,
        instruction_text=group_data.instruction_text,
        group_title=group_data.group_title,
        display_order=group_data.display_order
    )
    db.add(group_model)
    db.commit()
    db.refresh(group_model)
    
    return group_model

# Read All Groups for a Schedule
@admin_router.get("/schedules/{schedule_id}/groups", response_model=List[schemas.QuestionGroupDisplay])
async def read_question_groups(schedule_id: int, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """
    Retrieves all question groups (sections) for a specific exam schedule, ordered by display_order.
    """
    groups = db.query(models.QuestionGroup).filter(models.QuestionGroup.schedule_id == schedule_id).order_by(models.QuestionGroup.display_order).all()
    
    if not groups and not db.query(models.ExamSchedule).get(schedule_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam Schedule not found.")
        
    return groups

# Update Question Group
@admin_router.put("/groups/{group_id}", response_model=schemas.QuestionGroupDisplay)
async def update_question_group(group_id: int, group_data: schemas.QuestionGroup, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """
    Updates the details (instructions, title, order) of an existing question group.
    """
    group_model = db.query(models.QuestionGroup).filter(models.QuestionGroup.id == group_id).first()
    
    if not group_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question Group not found.")

    if group_model.display_order != group_data.display_order:
        existing_group_with_order = db.query(models.QuestionGroup).filter(
            models.QuestionGroup.schedule_id == group_model.schedule_id,
            models.QuestionGroup.display_order == group_data.display_order,
            models.QuestionGroup.id != group_id
        ).first()
        
        if existing_group_with_order:
             raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, 
                detail=f"Display order {group_data.display_order} is already used by another group in this schedule."
            )
    
    group_model.instruction_text = group_data.instruction_text
    group_model.group_title = group_data.group_title
    group_model.display_order = group_data.display_order
    
    db.commit()
    db.refresh(group_model)
    
    return group_model

# Delete Question Group
@admin_router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question_group(group_id: int, admin_user: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """
    Deletes a question group and cascades the deletion to all associated questions and options.
    """
    group_model = db.query(models.QuestionGroup).filter(models.QuestionGroup.id == group_id).first()
    
    if not group_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question Group not found.")

    question_ids = [q.id for q in group_model.questions]
    
    if question_ids:
        answer_count = db.query(models.UserAnswer).filter(models.UserAnswer.question_id.in_(question_ids)).count()
        
        if answer_count > 0:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Cannot delete group. {answer_count} answers are recorded against questions in this group. Delete the schedule first or archive this group."
            )
            
    db.delete(group_model)
    db.commit()
    
    return

