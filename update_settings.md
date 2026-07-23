# Update Settings — Settings Page Completion Report

This report documents the changes made to finish the **Settings** page of the admin dashboard. Only the Settings page and its supporting backend endpoints were modified — no other pages were touched.

## Objective

The Settings page should allow changing **only**:

- Assistant Name
- System Prompt
- Calendar File Upload
- Campaign List Excel Upload

It should display the current values for all of the above, keep the existing design, and upload files to the backend without parsing them in the frontend.

---

## Modified Files

### 1. `backend/main.py`

Backend endpoints and supporting logic for the Settings page.

#### Added constants

```python
# Allowed file extensions for settings uploads
CALENDAR_ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv", ".json"}
CAMPAIGN_LIST_ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}
```

#### `SettingsUpdateRequest` (restricted)

Removed `campaign_list_file` so the PUT endpoint only accepts editable text fields:

```python
class SettingsUpdateRequest(BaseModel):
    assistant_name: str | None = None
    system_prompt: str | None = None
```

#### Added helper functions

```python
def get_filename_from_path(path_str: str) -> str:
    """Extract just the filename from a stored file path."""
    if not path_str:
        return ""
    try:
        return Path(path_str).name
    except Exception:
        return path_str


def get_settings_for_display() -> dict[str, str]:
    """Return settings with file paths converted to filenames for display."""
    settings = get_all_settings()
    settings["calendar_file"] = get_filename_from_path(settings.get("calendar_file", ""))
    settings["campaign_list_file"] = get_filename_from_path(settings.get("campaign_list_file", ""))
    return settings
```

> The full path is still stored in the database so existing consumers (e.g. `date_utils.load_calendar_file()`) keep working. Only the API response returns the filename.

#### `GET /admin/settings`

Returns display-safe settings (filenames for file fields):

```python
@app.get("/admin/settings")
async def admin_get_settings():
    return get_settings_for_display()
```

#### `PUT /admin/settings`

Updates only `assistant_name` and `system_prompt`, then rebuilds the QA chain if it exists:

```python
@app.put("/admin/settings")
async def admin_update_settings(req: SettingsUpdateRequest):
    if req.assistant_name is not None:
        set_setting("assistant_name", req.assistant_name)
    if req.system_prompt is not None:
        set_setting("system_prompt", req.system_prompt)

    global qa_chain
    if qa_chain is not None:
        qa_chain = build_qa_chain_from_vectordb(vectordb)

    return {"ok": True, "settings": get_settings_for_display()}
```

#### `POST /admin/settings/calendar`

Validates extensions (XLSX, XLS, CSV, JSON), saves the file to `backend/calendar_files/`, stores the full path in settings, and returns the filename:

```python
@app.post("/admin/settings/calendar")
async def admin_upload_calendar(file: UploadFile = File(...)):
    filename = Path(file.filename or "calendar.json").name
    suffix = Path(filename).suffix.lower()

    if suffix not in CALENDAR_ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Supported calendar file types: XLSX, XLS, CSV, JSON.",
        )

    dest = Path(CALENDAR_DIR) / filename

    try:
        save_uploaded_file(file, dest)
    finally:
        await file.close()

    set_setting("calendar_file", str(dest))
    return {
        "ok": True,
        "calendar_file": filename,
        "message": "Calendar file uploaded successfully",
    }
```

#### `POST /admin/settings/campaign-list`

Validates extensions (XLSX, XLS, CSV), saves the file to `backend/calendar_files/`, stores the full path in settings, and returns the filename. The file is **not parsed** in the frontend or backend — only stored:

```python
@app.post("/admin/settings/campaign-list")
async def admin_upload_campaign_list(file: UploadFile = File(...)):
    filename = Path(file.filename or "campaign_list.xlsx").name
    suffix = Path(filename).suffix.lower()

    if suffix not in CAMPAIGN_LIST_ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Supported campaign list file types: XLSX, XLS, CSV.",
        )

    dest = Path(CALENDAR_DIR) / filename

    try:
        save_uploaded_file(file, dest)
    finally:
        await file.close()

    set_setting("campaign_list_file", str(dest))
    return {
        "ok": True,
        "campaign_list_file": filename,
        "message": "Campaign list file uploaded successfully",
    }
```

---

### 2. `backend/admin_dashboard.html`

Rewrote the `SettingsView` component into three cards, keeping the existing design language (same `.card`, `.drop-zone`, `.btn`, `.muted`, `.label` classes already used by the Knowledge Base page).

#### Added shared constants and validator

```js
const CALENDAR_ACCEPTED_EXTENSIONS = ['.xlsx', '.xls', '.csv', '.json'];
const CALENDAR_ACCEPT_ATTR = '.xlsx,.xls,.csv,.json';
const CAMPAIGN_LIST_ACCEPTED_EXTENSIONS = ['.xlsx', '.xls', '.csv'];
const CAMPAIGN_LIST_ACCEPT_ATTR = '.xlsx,.xls,.csv';

function validateSettingsFile(file, allowedExtensions, label) {
  if (!file) return false;
  const ext = '.' + (file.name.split('.').pop() || '').toLowerCase();
  if (!allowedExtensions.includes(ext)) {
    return false;
  }
  return true;
}
```

#### `SettingsView` layout

1. **Assistant Name + System Prompt** — editable form with a Save button. Only these two fields are sent on save.
2. **Calendar File** — drag-and-drop upload zone accepting Excel/CSV/JSON, with client-side validation and a "Current Calendar File" filename display.
3. **Campaign List File** — drag-and-drop upload zone accepting XLSX/XLS/CSV, with client-side validation and a "Current Campaign List File" filename display.

The page displays:

- Current Assistant Name
- Current System Prompt
- Current Calendar filename
- Current Campaign List filename

#### Save behavior

Only editable fields are sent to the backend:

```js
const payload = {
  assistant_name: settings.assistant_name || '',
  system_prompt: settings.system_prompt || '',
};
const data = await apiSend('/admin/settings', 'PUT', payload);
setSettings((prev) => ({ ...prev, ...data.settings }));
```

#### Upload behavior

Each upload uses `FormData`, validates the extension client-side before sending, shows an uploading state, and updates the displayed filename from the backend response.

---

## New Upload Components

- **Calendar upload drop-zone** (inline in `SettingsView`) — supports drag-and-drop and click-to-select, validates `.xlsx/.xls/.csv/.json`.
- **Campaign list upload drop-zone** (inline in `SettingsView`) — supports drag-and-drop and click-to-select, validates `.xlsx/.xls/.csv`.

Both reuse the existing `.drop-zone` styling from the Knowledge Base page to keep the design consistent.

---

## Backend Endpoints (reused, no new routes)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/admin/settings` | Returns current settings (filenames for file fields) |
| PUT | `/admin/settings` | Updates only `assistant_name` and `system_prompt` |
| POST | `/admin/settings/calendar` | Stores uploaded calendar file (Excel/CSV/JSON) |
| POST | `/admin/settings/campaign-list` | Stores uploaded campaign list (XLSX/XLS/CSV) without parsing |

Files are saved into `backend/calendar_files/` using the existing `save_uploaded_file` helper.

---

## Verification

- `backend/main.py` Python syntax validated successfully.
- No other pages (Dashboard, Knowledge Base, Campaigns, Reports) were modified.
- Existing design tokens and components reused — no new CSS framework or styles introduced.