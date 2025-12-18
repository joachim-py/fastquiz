from datetime import datetime, date, time
from pydantic import BaseModel, computed_field, model_validator
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
    question_number: int
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
    instruction_text: str
    group_title: Optional[str] = None
    display_order: int
    
class QuestionGroupDisplay(QuestionGroup):
    """Schema for displaying a Group to the Admin."""
    id: int
    schedule_id: int
    questions: List[QuestionStudentDisplay] = [] 
    
    class ConfigDict:
        from_attributes = True    
    
class QuestionGroupStudentDisplay(QuestionGroup):
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
        return round((self.correct_answers / self.total_answered_questions) * 100, 2)

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
    student_class: Optional['ClassDisplay'] = None
    class_name: Optional[str] = None
    
    
    @model_validator(mode='before')
    @classmethod
    def extract_student_relations(cls, data):
        # Handle cases where data is an ORM object or a dict
        student_class = getattr(data, 'student_class', None)
        if student_class:
            # Manually inject class_name for convenience
            if isinstance(data, dict):
                data['class_name'] = student_class.name
            else:
                setattr(data, 'class_name', student_class.name)
        return data
    
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
    id: int
    subject_id: int
    class_id: int
    exam_date: date
    start_time: time
    duration_minutes: int
    subject: Optional[SubjectDisplay] = None
    exam_class: Optional[ClassDisplay] = None
    exam_password: str
    
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
    
