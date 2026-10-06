# מדריך הרצה (Windows, CMD)

## פעם ראשונה

1. חלץ את קובץ ה-ZIP לתיקייה, למשל `C:\projects\deepfake-detection-system`.
2. פתח את התיקייה ב-VS Code: File > Open Folder.
3. פתח טרמינל CMD בתוך VS Code: Terminal > New Terminal, ובחץ שליד סימן ה-+ בחר Command Prompt.
4. הרץ את הפקודות אחת אחרי השנייה:

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python scripts\init_env.py
flask --app run seed-demo
python run.py
```

| פקודה | מה היא עושה |
| --- | --- |
| `python -m venv venv` | יוצרת סביבה וירטואלית: תיקייה נפרדת לספריות של הפרויקט |
| `venv\Scripts\activate` | מפעילה את הסביבה. בתחילת השורה יופיע `(venv)` |
| `pip install -r requirements.txt` | מתקינה את כל הספריות בגרסאות שנבדקו |
| `python scripts\init_env.py` | יוצרת קובץ `.env` עם מפתח סודי אקראי |
| `flask --app run seed-demo` | יוצרת את מסד הנתונים, משתמשי דמו ו-25 ניתוחים לדוגמה |
| `python run.py` | מפעילה את השרת |

5. פתח בדפדפן את הכתובת http://127.0.0.1:5000 והתחבר עם `admin@globaltech.com` והסיסמה `Demo1234!`.

## בפעמים הבאות

```bat
venv\Scripts\activate
python run.py
```

## בדיקה ראשונה מומלצת

1. **Reference identities:** הוסף את עצמך עם תמונה ברורה מהטלפון, למשל עם התפקיד "CEO".
2. **Live analysis:** בחר את עצמך ב-"Participant claims to be" והפעל Camera. אמורה להופיע מסגרת סביב הפנים ותוצאה.
3. חזור על אותו דבר עם אדם אחר מול המצלמה, או עם תמונה של אדם אחר בטלפון. התאמת הזהות צריכה לרדת.
4. **Share a window:** פתח סרטון ביוטיוב או שיחת Zoom, בחר את החלון, ובדוק שהמערכת מנתחת את מי שמופיע בו.
5. **Dashboard, Logs, Alerts:** בדוק שהכול נשמר ומתעדכן.

## כיול אימות הזהות (חשוב לפני הדמו)

ב-Live analysis רשום את ערך Identity match כשאתה מול המצלמה, וכשאדם אחר מול המצלמה.
אם אתה מקבל פחות מ-45 מול התמונה של עצמך, צלם תמונת ייחוס בתנאי תאורה דומים למצלמה.
הספים נמצאים ב-`config.py` (`IDENTITY_OK`, `IDENTITY_REJECT`) ובפונקציה `identity_match_score` שב-`app/services/faces.py`.
תעד את הערכים שקיבלת. זה חומר לפרק הבדיקות בדוח.

## בדיקות אוטומטיות

```bat
pytest -v
```

אמורות לעבור 41 בדיקות.

## תקלות נפוצות

קודם כל הרץ בדיקה עצמית. היא בודקת את המודלים, את התיקיות ואת מסד הנתונים, ומדפיסה מה לא תקין:

```bat
flask --app run doctor
```

אם מופיעה שגיאה 500 בדפדפן, הפירוט המלא (Traceback) מודפס בחלון ה-CMD שבו רץ `python run.py`.

| הודעה | פתרון |
| --- | --- |
| `metadata-generation-failed` על numpy בזמן `pip install` | גרסת Python חדשה מדי. עדכן לגרסה האחרונה של `requirements.txt`, או צור venv עם Python 3.12 |
| שגיאה בהעלאת תמונה, או `FAIL Project folder path` | בנתיב התיקייה יש עברית (למשל שם משתמש בעברית או "שולחן העבודה"). העבר את הפרויקט ל-`C:\projects\deepfake-detection-system`, מחק את תיקיית `venv` וצור אותה מחדש |
| `'python' is not recognized` | Python לא מוגדר ב-PATH. נסה `py` במקום `python` |
| `activate` לא עובד ב-PowerShell | עבור ל-CMD, או הרץ `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `Address already in use` | השרת כבר רץ בחלון אחר. סגור אותו או לחץ Ctrl+C |
| המצלמה לא נפתחת | אשר גישה למצלמה בדפדפן, וסגור את Zoom או Teams אם הם תופסים אותה |
| "only allows camera on https or localhost" | היכנס דרך `http://127.0.0.1:5000` ולא דרך כתובת IP |

## העלאה ל-GitHub

צור repository ריק בשם `deepfake-detection-system` ב-GitHub, בלי README. אחר כך הרץ:

```bat
git init
git add .
git status
git commit -m "Initial working prototype: Flask IS + deepfake pipeline"
git branch -M main
git remote add origin https://github.com/<USERNAME>/deepfake-detection-system.git
git push -u origin main
```

לפני ה-commit בדוק ב-`git status` ש-`.env`, `venv` ו-`instance` **לא** מופיעים ברשימה. `.gitignore` אמור לדאוג לזה.
