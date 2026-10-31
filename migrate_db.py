import sqlite3

DB_PATH = "data/study_assistant.db"

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 临时表：备份旧数据
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions_backup AS 
        SELECT * FROM questions
    """)
    conn.commit()
    
    # 删除旧表
    cursor.execute("DROP TABLE questions")
    
    # 重建新表（去掉 CHECK 约束）
    cursor.execute("""
        CREATE TABLE questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            topic TEXT,
            grade TEXT,
            question_type TEXT,
            difficulty TEXT,
            score INTEGER DEFAULT 3,
            content TEXT NOT NULL,
            option_a TEXT,
            option_b TEXT,
            option_c TEXT,
            option_d TEXT,
            answer TEXT NOT NULL,
            analysis TEXT,
            step_rules TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    
    # 恢复数据
    cursor.execute("""
        INSERT INTO questions (
            id, user_id, subject, topic, grade, question_type, difficulty,
            score, content, option_a, option_b, option_c, option_d,
            answer, analysis, step_rules, created_at, updated_at
        )
        SELECT 
            id, user_id, subject, topic, grade, question_type, difficulty,
            score, content, option_a, option_b, option_c, option_d,
            answer, analysis, step_rules, created_at, updated_at
        FROM questions_backup
    """)
    
    # 删除备份表
    cursor.execute("DROP TABLE questions_backup")
    
    conn.commit()
    conn.close()
    print("✅ 重建完成，CHECK 约束已移除")

if __name__ == "__main__":
    migrate()