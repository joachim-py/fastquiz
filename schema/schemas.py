from datetime import datetime, date, time
from pydantic import BaseModel, Field, computed_field
from typing import List, Optional

# Option
class Option(BaseModel):
    """Defines a single answer option."""
    option_text: str
    is_correct: bool

class OptionStudentDisplay(BaseModel):
    id: int
    option_text: str
    
    class ConfigDict:
        from_attributes = True

# Question
class Question(BaseModel):
    """Defines a single quiz question."""
    question_text: str
    options: List[Option]

class QuestionStudentDisplay(BaseModel):
    id: int
    group_id: int
    question_number: int
    question_text: str
    options: List[OptionStudentDisplay]
    
    class ConfigDict:
        from_attributes = True


class QuestionGroup(BaseModel):
    """Base schema for creating or updating a Question Group."""
    instruction_text: str
    group_title: Optional[str] = None
    display_order: int
    
class QuestionGroupDisplay(QuestionGroup):
    """Schema for displaying a Group to the Admin."""
    id: int
    schedule_id: int
    
    class ConfigDict:
        from_attributes = True    
    
class QuestionGroupStudentDisplay(QuestionGroup):
    """
    Schema for displaying a Group to the student during the exam load.
    Includes the nested list of questions.
    """
    id: int
    questions: List['QuestionStudentDisplay'] = []
    
    class ConfigDict:
        from_attributes = True

# Subject
class Subject(BaseModel):
    """Defines a quiz subject that contains a list of questions."""
    name: str

class SubjectDisplay(BaseModel):
    id: int
    name: str
    
    @computed_field
    @property
    def question_count(self) -> int:
        if hasattr(self, 'questions') and self.questions is not None:
             return len(self.questions)
        return 0 
    
    class Config:
        from_attributes = True

class SubjectScoreDetail(BaseModel):
    subject_id: int
    subject_name: str
    correct_answers: int
    total_answered_questions: int 
    
    @computed_field
    @property
    def subject_percentage(self) -> float:
        if self.total_answered_questions == 0:
            return 0.0
        return (self.correct_answers / self.total_answered_questions) * 100

# Student
class Student(BaseModel):
    """Schema for enrolling a new student."""
    full_name: str
    reg_number: str
    class_id: int

class StudentDisplay(BaseModel):
    id: int
    full_name: str
    reg_number: str
    class_id: int
    
    class Config:
        from_attributes = True


# Class
class Class(BaseModel):
    name: str

class ClassDisplay(BaseModel):
    id: int
    name: str
    
    class Config:
        from_attributes = True

# Exam Schedule
class ExamSchedule(BaseModel):
    subject_id: int
    class_id: int
    exam_date: date
    start_time: time
    duration_minutes: int
    exam_password: str

class ExamScheduleDisplay(BaseModel):
    """Display model for one scheduled exam instance (e.g., SS1 English on 11/12/2025)."""
    id: int
    subject_id: int
    class_id: int
    exam_date: date
    start_time: time
    duration_minutes: int
    subject_name: str
    
    class Config:
        from_attributes = True

class ScheduledExamStatus(BaseModel):
    schedule_id: int
    subject_name: str
    duration_minutes: int
    start_time: time
    attempt_id: Optional[int] = None
    status_color: str
    is_clickable: bool
    
    class Config:
        from_attributes = True

class ExamScheduleDashboard(BaseModel):
    id: int
    subject_id: int
    subject_name: str
    class_id: int
    exam_date: date
    start_time: time
    duration_minutes: int
    number_of_groups: int = 0
    total_questions: int = 0
    
    class ConfigDict:
        from_attributes = True

# Auth
class ExamLoginInput(BaseModel):
    reg_number: str
    exam_password: str

class ExamAuthToken(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    student_id: int
    class_id: int
    schedule_id: Optional[int] = None
    sub: Optional[str] = None
    
class ExamStartResponse(BaseModel):
    attempt_id: int
    schedule_id: int
    subject_name: str
    duration_minutes: int
    question_groups: List[QuestionGroupStudentDisplay]
    total_questions: int
    
    class ConfigDict:
        from_attributes = True
   
# Answers and Report
class AnswerInput(BaseModel):
    question_id: int
    selected_option_id: int 

class UserAnswer(BaseModel):
    id: int
    attempt_id: int
    question_id: int
    selected_option_id: int
    is_correct: bool
    correct_option_id: int 
    answered_at: datetime 
    
    class Config:
        from_attributes = True    

class ExamResult(BaseModel):
    attempt_id: int
    final_score: int
    total_questions: int
    percentage_score: float
    time_taken_seconds: int
    is_time_up_submission: bool
    subject_report: SubjectScoreDetail 
    
    class Config:
        from_attributes = True

class AnswerValidationResponse(BaseModel):
    is_correct: bool
    correct_option_id: int
    user_selected_option_id: int
    attempt_id: Optional[int] = None 
    score_updated: bool = True
    
