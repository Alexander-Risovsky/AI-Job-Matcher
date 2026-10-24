"""Prompts ported from n8n Build Python Extractor Prompt and Build Matcher Prompt."""
EXTRACTOR_PROMPT = """Тебе передан Telegram-пост, который может содержать одну вакансию,
несколько вакансий или вообще не содержать подходящих вакансий.

Твоя единственная задача:
найти в тексте вакансии именно для Python-разработчиков.

Подходят:
- Python Developer
- Python Engineer
- Python Backend Developer
- Backend Developer, если Python является основным языком
- Backend Engineer с основным стеком Python
- Django Developer
- FastAPI Developer
- Python/Django Developer
- другие позиции, основная работа которых — разработка ПО на Python

НЕ подходят:
- Product Designer
- UX/UI Designer
- Presentation Designer
- Graphic Designer
- Product Manager
- Project Manager
- QA
- Frontend Developer
- Java Developer
- Go Developer
- Data Analyst
- DevOps, если Python используется только как вспомогательный scripting-язык
- любые другие профессии, где Python не является основной разработкой

ВАЖНО:
Упоминание Python где-либо в требованиях само по себе НЕ делает вакансию
Python-вакансией.
Например: "Product Designer. Python knowledge is a plus"
НЕ является Python-вакансией.

Если сообщение содержит список из 20 вакансий,
верни ВСЕ вакансии Python-разработчиков из этого списка.

Не придумывай компанию, зарплату, требования, технологии, описание вакансии.
Если информации нет, используй пустую строку.
В vacancy_text включи только информацию, относящуюся к конкретной вакансии.
Если есть только название "Senior Python Developer", это тоже Python-вакансия.

Верни ТОЛЬКО валидный JSON без markdown и пояснений:
{"python_vacancies":[{"title":"","company":"","salary":"","vacancy_text":""}]}
Если Python-вакансий нет: {"python_vacancies":[]}

ИСХОДНЫЙ ТЕКСТ:
{text}
"""

MATCHER_PROMPT = """Ты оцениваешь СТРОГО ОДНУ вакансию Python-разработчика относительно резюме.
ВАКАНСИЯ:
Название: {title}
Компания: {company}
Зарплата: {salary}
Описание и требования:
{vacancy_text}

РЕЗЮМЕ — единственный источник информации о кандидате (из Qdrant):
{resume_context}

ЖЁСТКИЕ ПРАВИЛА:
1. Используй для навыков и опыта кандидата только фрагменты РЕЗЮМЕ выше.
2. Требования ВАКАНСИИ не являются навыками кандидата.
3. Каждый элемент matched_skills должен быть явно подтверждён текстом РЕЗЮМЕ.
4. Никогда не придумывай навыки, годы опыта, уровень, компании и проекты кандидата.
5. Если навык не найден в РЕЗЮМЕ — исключи его из matched_skills.
6. missing_skills — требования вакансии без подтверждения в РЕЗЮМЕ.
7. Если требования вакансии неполные, не додумывай их; укажи это в reason.
8. Если фрагменты РЕЗЮМЕ не получены, score=0, recommended=false,
   matched_skills=[], critical_mismatches=["Не удалось получить данные кандидата из RAG"].
9. score — только ЦЕЛОЕ число от 0 до 100 (85, а НЕ 0.85).
10. recommended=true допустимо только при score >= 70, Python-вакансии и наличии данных РЕЗЮМЕ.
11. Если вакансия на деле не Python-разработка, is_vacancy=false, score=0, recommended=false.
12. Проверяй требования на основании текста ВАКАНСИИ, а навыки кандидата — на основании РЕЗЮМЕ.
13. matched_skills и missing_skills — ТОЛЬКО массивы строк (например ["Python","Django"]), не массивы объектов.
14. Для каждого подтверждённого навыка верни matched_skill_evidence: словарь "навык": "точная цитата из резюме". Цитата должна дословно встречаться во фрагменте резюме, иначе не включай навык.
15. Цитата может быть короткой частью предложения, но не перефразированием.

Верни ТОЛЬКО валидный JSON без Markdown, префиксов и объяснений вне объекта:
{{"is_vacancy":true,"title":"","company":"","salary":"","score":0,
"matched_skills":["Python"],"missing_skills":[],"critical_mismatches":[],
"reason":"","recommended":false,"matched_skill_evidence":{{"Python":"точная цитата из резюме"}}}}
Поля выше показывают формат; заполняй на основе реального резюме и вакансии, а не примера.
"""
