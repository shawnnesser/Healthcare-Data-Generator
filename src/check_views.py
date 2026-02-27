import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'src')
from config import CONNECTION_STRING
from sqlalchemy import create_engine, text

def main():
    engine = create_engine(f"mssql+pyodbc:///?odbc_connect={CONNECTION_STRING}")
    with engine.connect() as conn:
        q = "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.VIEWS WHERE TABLE_NAME IN ('vw_current_er_beds','vw_current_patient_beds')"
        res = conn.execute(text(q)).fetchall()
        if not res:
            print('NOT FOUND')
        else:
            for r in res:
                print(r[0], r[1])

if __name__ == '__main__':
    main()
