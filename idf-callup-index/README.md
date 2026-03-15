# מה הסיכוי שגדוד 9260 יוקפץ

הסקריפט מחשב פעם ביום ציון `0-100` לסבירות הקפצה של גדוד תותחנים מאוגדה 36 לפי ידיעות עדכניות.

## מה המדד מחשב

המדד מורכב מאותות משוקללים:

- `fire_from_lebanon` - ירי/אזעקות מהצפון
- `idf_strikes_in_lebanon` - קצב תקיפות צה"ל בלבנון
- `ground_campaign_indicators` - אינדיקציות לתמרון קרקעי
- `reserve_mobilization` - גיוס מילואים / צו 8
- `decision_maker_signals` - איתותים מהדרג המדיני-ביטחוני
- `multi_front_pressure` - לחץ רב-זירתי
- `division_36_specific` - אזכורים ישירים לאוגדה 36 / עוצבת געש / תותחנים

בנוסף יש `wide_campaign_boost` כאשר מזוהות ידיעות על "מערכה רחבה".

## הרצה מקומית

```bash
cd /Users/oz/Documents/GitHub/codex/idf-callup-index
python3 daily_callup_index.py --offline-demo --out-dir .
```

להרצה אמיתית עם משיכת פידים:

```bash
cd /Users/oz/Documents/GitHub/codex/idf-callup-index
python3 daily_callup_index.py --out-dir .
```

להערכת תרחיש שבו כבר החלה מערכה רחבה בלבנון:

```bash
python3 daily_callup_index.py --out-dir . --assume-wide-campaign
```

## פלטים

- `data/latest_index.json` - התוצאה האחרונה
- `data/history.csv` - היסטוריית ציונים יומית
- `reports/daily_report_YYYY-MM-DD.md` - דוח יומי לקריאה
- `docs/` - אתר סטטי ל-GitHub Pages

## עדכון יומי אוטומטי

אפשר לתזמן פעם ביום (08:00 שעון ישראל) בעזרת automation של Codex או cron.
דוגמה ל-cron:

```cron
0 8 * * * cd /Users/oz/Documents/GitHub/codex/idf-callup-index && /usr/bin/python3 daily_callup_index.py --out-dir . >> data/cron.log 2>&1
```

## העלאה כאתר GitHub Pages

1. יש Workflow מוכן בקובץ:
   - `.github/workflows/idf-9260-pages.yml`
2. ב-GitHub, תחת `Settings -> Pages`, ודא ש-`Source` הוא `GitHub Actions`.
3. להפעלה ידנית:
   - `Actions -> Publish 9260 Call-up Index -> Run workflow`
4. עדכון אוטומטי:
   - רץ כל יום לפי cron (`05:00 UTC`).

האתר נטען מתוך `idf-callup-index/docs` וקורא נתונים מ-`docs/data/latest_index.json` ו-`docs/data/history.csv`.

## צריך לעדכן ידנית?

לא לעדכון שוטף: אחרי ש-GitHub Actions פעיל, המדד מתעדכן אוטומטית כל יום והאתר נבנה מחדש עם הנתונים העדכניים.

עדכון ידני נדרש רק אם רוצים להוסיף/לשנות "אות ידני" (ידיעת איכות עם בוסט חריג):

1. ערוך את `data/manual_signals.json`.
2. הוסף/עדכן פריט עם השדות:
   - `title`
   - `url`
   - `boost` (למשל 10-20)
   - `expires_on` בפורמט `YYYY-MM-DD`
3. בצע `commit` ו-`push`.
4. הרץ ידנית את `Publish 9260 Call-up Index` או המתן לריצה היומית.

באתר עצמו מופיע שדה `תאריך עדכון אחרון`, מתוך `latest_index.json`, כדי לוודא מתי בפועל הריצה האחרונה התבצעה.
