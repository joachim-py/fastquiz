from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, DateTime, Date, Time
from sqlalchemy.orm import Mapped, relationship
from config.database import Base
from datetime import datetime, date, time
from typing import Optional, List

class Class(Base):
    __tablename__ = "classes"
    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    name: Mapped[str] = Column(String, unique=True, nullable=False)
    students: Mapped[List['Student']] = relationship("Student", back_populates="student_class")
    schedules: Mapped[List['ExamSchedule']] = relationship("ExamSchedule", back_populates="exam_class")

class Student(Base):
    __tablename__ = "students"
    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    full_name: Mapped[str] = Column(String, index=True, nullable=False)
    reg_number: Mapped[str] = Column(String, unique=True, index=True, nullable=False)
    class_id: Mapped[int] = Column(Integer, ForeignKey("classes.id"))
    student_class: Mapped['Class'] = relationship("Class", back_populates="students")
    attempts: Mapped[List['ScheduledAttempt']] = relationship("ScheduledAttempt", back_populates="student")

class ExamSchedule(Base):
    __tablename__ = "exam_schedules"
    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    subject_id: Mapped[int] = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    class_id: Mapped[int] = Column(Integer, ForeignKey("classes.id"), nullable=False)
    exam_date: Mapped[date] = Column(Date, nullable=False)
    start_time: Mapped[time] = Column(Time, nullable=False)
    duration_minutes: Mapped[int] = Column(Integer, nullable=False)
    exam_password: Mapped[str] = Column(String, nullable=False) 
    subject: Mapped['Subject'] = relationship("Subject", back_populates="schedules")
    exam_class: Mapped['Class'] = relationship("Class", back_populates="schedules")
    attempts: Mapped[List['ScheduledAttempt']] = relationship("ScheduledAttempt", back_populates="schedule")
    question_groups: Mapped[List["QuestionGroup"]] = relationship("QuestionGroup", back_populates="schedule", order_by="QuestionGroup.display_order", cascade="all, delete-orphan")

class ScheduledAttempt(Base):
    __tablename__ = "scheduled_attempts"
    id: Mapped[int] = Column(Integer, primary_key=True, index=True) 
    student_id: Mapped[int] = Column(Integer, ForeignKey("students.id"), nullable=False) 
    schedule_id: Mapped[int] = Column(Integer, ForeignKey("exam_schedules.id"), nullable=False)
    start_time: Mapped[datetime] = Column(DateTime, default=datetime.utcnow)
    end_time: Mapped[Optional[datetime]] = Column(DateTime, nullable=True)
    score: Mapped[int] = Column(Integer, default=0) 
    student: Mapped['Student'] = relationship("Student", back_populates="attempts")
    schedule: Mapped['ExamSchedule'] = relationship("ExamSchedule", back_populates="attempts")
    answers: Mapped[List['UserAnswer']] = relationship("UserAnswer", back_populates="attempt", cascade="all, delete-orphan")
    final_report: Mapped['FinalReport'] = relationship("FinalReport", back_populates="attempt", uselist=False)

class UserAnswer(Base):
    __tablename__ = "user_answers"
    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    attempt_id: Mapped[int] = Column(Integer, ForeignKey("scheduled_attempts.id"))
    question_id: Mapped[int] = Column(Integer, ForeignKey("questions.id"))
    selected_option_id: Mapped[int] = Column(Integer, ForeignKey("options.id"))
    is_correct: Mapped[bool] = Column(Boolean, default=False)
    correct_option_id: Mapped[int] = Column(Integer, ForeignKey("options.id"))
    answered_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow)
    attempt: Mapped['ScheduledAttempt'] = relationship("ScheduledAttempt", back_populates="answers")

class FinalReport(Base):
    __tablename__ = "final_reports"
    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    attempt_id: Mapped[int] = Column(Integer, ForeignKey("scheduled_attempts.id"), unique=True, nullable=False)
    subject_scores_json: Mapped[str] = Column(String, nullable=False)
    final_score: Mapped[int] = Column(Integer, nullable=False)
    time_taken_seconds: Mapped[int] = Column(Integer, nullable=False)
    attempt: Mapped['ScheduledAttempt'] = relationship("ScheduledAttempt", back_populates="final_report")

class Option(Base):
    __tablename__ = "options"
    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    option_text: Mapped[str] = Column(String, nullable=False)
    question_id: Mapped[int] = Column(Integer, ForeignKey("questions.id"))
    question: Mapped['Question'] = relationship("Question", back_populates="options", foreign_keys=[question_id])

class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    question_text: Mapped[str] = Column(String, nullable=False)
    correct_option_id: Mapped[int] = Column(Integer, ForeignKey("options.id"))
    question_number: Mapped[int] = Column(Integer, nullable=False)
    group_id: Mapped[int] = Column(ForeignKey("question_groups.id"), nullable=False)
    group: Mapped["QuestionGroup"] = relationship("QuestionGroup", back_populates="questions")
    correct_option: Mapped['Option'] = relationship("Option", foreign_keys=[correct_option_id])
    options: Mapped[List[Option]] = relationship("Option", back_populates="question", foreign_keys=[Option.question_id], cascade="all, delete-orphan")

class QuestionGroup(Base):
    __tablename__ = "question_groups"
    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    schedule_id: Mapped[int] = Column(ForeignKey("exam_schedules.id"), nullable=False)
    instruction_text: Mapped[str] = Column(String, nullable=False)
    group_title: Mapped[Optional[str]] = Column(String, nullable=True) 
    display_order: Mapped[int] = Column(Integer, nullable=False) 
    schedule: Mapped["ExamSchedule"] = relationship("ExamSchedule", back_populates="question_groups")
    questions: Mapped[List["Question"]] = relationship("Question", back_populates="group", cascade="all, delete-orphan")

class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    name: Mapped[str] = Column(String, nullable=False)
    schedules: Mapped[List["ExamSchedule"]] = relationship(back_populates="subject")
    
