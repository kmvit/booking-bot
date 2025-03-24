from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Float, Date, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime
from config import DATABASE_URL

Base = declarative_base()

class Client(Base):
    __tablename__ = 'clients'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    username = Column(String)
    name = Column(String)
    phone = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    appointments = relationship("Appointment", back_populates="client")

class Procedure(Base):
    __tablename__ = 'procedures'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    duration = Column(Float)  # длительность в часах
    description = Column(String)
    appointments = relationship("Appointment", back_populates="procedure")

class Appointment(Base):
    __tablename__ = 'appointments'
    
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey('clients.id'))
    procedure_id = Column(Integer, ForeignKey('procedures.id'))
    date = Column(DateTime)
    status = Column(String, default='scheduled')  # scheduled, completed, cancelled
    created_at = Column(DateTime, default=datetime.utcnow)
    reminder_sent = Column(Boolean, default=False)
    
    client = relationship("Client", back_populates="appointments")
    procedure = relationship("Procedure", back_populates="appointments")

class InactiveSlot(Base):
    __tablename__ = 'inactive_slots'
    
    id = Column(Integer, primary_key=True)
    date = Column(Date)
    time = Column(String)  # время в формате "HH:MM"
    is_weekend = Column(Boolean, default=False)  # True для субботы и воскресенья
    
    __table_args__ = (
        UniqueConstraint('date', 'time', name='uix_date_time'),
    )

# Создание подключения к базе данных
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Создание таблиц
Base.metadata.create_all(bind=engine)

# Инициализация процедур при первом запуске
def init_procedures():
    db = SessionLocal()
    try:
        # Проверяем, есть ли уже процедуры
        if db.query(Procedure).count() == 0:
            procedures = [
                Procedure(
                    name="Эстетика (уход, чистка, пилинг и пр.)",
                    duration=1.5,
                    description="Комплексные процедуры по уходу за кожей"
                ),
                Procedure(
                    name="Контурная пластика губ",
                    duration=1.0,
                    description="Процедура увеличения объема губ"
                ),
                Procedure(
                    name="Биоревитализация",
                    duration=1.0,
                    description="Процедура омоложения кожи"
                )
            ]
            for procedure in procedures:
                db.add(procedure)
            db.commit()
    finally:
        db.close()

# Инициализируем процедуры при импорте модуля
init_procedures() 