"""Hand-written copy for the YouTube-to-Library path; no machine translation."""


def youtube_actions(language: str) -> dict[str, str]:
    if language == 'fa':
        return {
            'save': '➕ ذخیره در کتابخانه',
            'watch': '▶️ تماشای ویدیو',
            'assign': '🎯 وصل کردن به کار',
            'new_task': '📝 ساخت کار جدید',
            'transcript': 'متن زیرنویس',
        }
    return {
        'save': '➕ Save to Library',
        'watch': '▶️ Watch video',
        'assign': '🎯 Assign to Task',
        'new_task': '📝 New One-Time Task',
        'transcript': 'Get Transcript',
    }


def persian_video_card(info: dict) -> str:
    title = str(info.get('title') or 'ویدیوی یوتیوب').strip()
    if len(title) > 120:
        title = title[:117] + '…'
    lines = ['🎬 ویدیو رو گرفتم!', '', title]
    if info.get('channel'):
        lines.append(f"کانال: {info['channel']}")
    seconds = info.get('duration_seconds')
    if seconds and seconds > 0:
        minutes, seconds = divmod(int(seconds), 60)
        lines.append(f'مدت: {minutes}:{seconds:02d}')
    lines.extend(['', 'همین حالا تماشاش کن یا برای بعد توی «کتابخانه» ذخیره‌اش کن.'])
    return '\n'.join(lines)
