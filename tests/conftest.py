import sys
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.database import Base, Client, Procedure
from datetime import datetime

# Добавляем корневую директорию проекта в путь импорта
root_dir = Path(__file__).parent.parent
sys.path.append(str(root_dir))

# Создаем тестовую базу данных в памяти
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session")
def db_engine():
    """Создание тестового движка базы данных"""
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def db_session(db_engine):
    """Создание тестовой сессии базы данных"""
    session = TestingSessionLocal()
    
    try:
        yield session
    finally:
        session.rollback()
        session.close() 

@pytest.fixture
def test_procedure(db_session):
    """Фикстура для создания тестовой процедуры"""
    # Добавляем временную метку к имени процедуры, чтобы сделать его уникальным
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    procedure = Procedure(
        name=f"Тестовая процедура {timestamp}",
        duration=1.0,
    )
    db_session.add(procedure)
    db_session.commit()
    return procedure

@pytest.fixture
def test_client(db_session):
    """Фикстура для создания тестового клиента"""
    client = Client(
        name="Тестовый клиент",
        username="test_user",
        phone="+79001234567"
    )
    db_session.add(client)
    db_session.commit()
    return client