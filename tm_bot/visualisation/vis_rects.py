from dataclasses import dataclass, field
from typing import List, Dict, Any
from datetime import date
import math

# ---------- Data models ----------

@dataclass
class Session:
    label: str      # e.g. 'Mon', 'Tue', 'Session 1'
    duration: float # hours spent in this session

@dataclass
class Task:
    emoji: str = ""  # Optional emoji for status
    code: str = ""   # P01, T02, ... (optional, can be empty)
    name: str = ""   # Promise text
    promised: float = 0.0  # promised hours
    filled: float = 0.0     # total hours done (sum of sessions)
    sessions: List[Session] = field(default_factory=list)  # ordered sequence

@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float
    task: Task

# ---------- Data conversion from reports service ----------

def _get_day_label(action_date: date) -> str:
    """Convert date to day label (Mon, Tue, etc.)."""
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return day_names[action_date.weekday()]

def _get_status_emoji(progress: float) -> str:
    """Get emoji based on progress percentage."""
    if progress >= 90:
        return "✅"
    elif progress >= 60:
        return "🟡"
    elif progress >= 30:
        return "🟠"
    else:
        return "🔴"

def create_tasks_from_summary(summary: Dict[str, Any]) -> List[Task]:
    """Convert report summary dict to Task objects with per-day sessions."""
    tasks: List[Task] = []
    
    for promise_id, data in summary.items():
        hours_promised = data.get('hours_promised', 0.0)
        hours_spent = data.get('hours_spent', 0.0)
        promise_text = data.get('text', '')
        sessions_data = data.get('sessions', [])
        
        # Calculate progress for emoji
        progress = (hours_spent / hours_promised * 100) if hours_promised > 0 else 0
        emoji = _get_status_emoji(progress)
        
        # Convert sessions data to Session objects
        sessions: List[Session] = []
        for sess_data in sessions_data:
            action_date = sess_data.get('date')
            hours = sess_data.get('hours', 0.0)
            if hours > 0 and action_date:
                day_label = _get_day_label(action_date)
                sessions.append(Session(label=day_label, duration=hours))
        
        # Create task
        task = Task(
            emoji=emoji,
            code=promise_id,
            name=promise_text,
            promised=hours_promised,
            filled=hours_spent,
            sessions=sessions
        )
        tasks.append(task)
    
    return tasks

# ---------- Treemap layout (squarified) ----------

def layout_treemap(tasks: List[Task], W: float, H: float) -> List[Rect]:
    total = sum(t.promised for t in tasks)
    if total <= 0:
        return []

    items = [
        (t, t.promised / total * W * H)
        for t in tasks
        if t.promised > 0
    ]
    items.sort(key=lambda x: x[1], reverse=True)

    rects: List[Rect] = []
    x, y, w, h = 0.0, 0.0, float(W), float(H)
    row: List[tuple[Task, float]] = []

    def worst_aspect_ratio(row_areas, length):
        if not row_areas:
            return math.inf
        s = sum(row_areas)
        if length <= 0:
            return math.inf
        depth = s / length
        worst = 0.0
        for a in row_areas:
            other = a / depth
            r = max(depth / other, other / depth)
            worst = max(worst, r)
        return worst

    while items:
        task, area = items[0]
        new_row_areas = [a for _, a in row] + [area]
        horizontal = (w >= h)
        length = w if horizontal else h

        if row and worst_aspect_ratio(new_row_areas, length) > worst_aspect_ratio([a for _, a in row], length):
            s = sum(a for _, a in row)
            if s == 0:
                break

            if horizontal:
                row_height = s / w
                cur_x = x
                for (rt, ra) in row:
                    rw = ra / row_height
                    rects.append(Rect(cur_x, y, rw, row_height, rt))
                    cur_x += rw
                y += row_height
                h -= row_height
            else:
                row_width = s / h
                cur_y = y
                for (rt, ra) in row:
                    rh = ra / row_width
                    rects.append(Rect(x, cur_y, row_width, rh, rt))
                    cur_y += rh
                x += row_width
                w -= row_width

            row = []
        else:
            row.append((task, area))
            items.pop(0)

    # remaining row
    if row:
        s = sum(a for _, a in row)
        if s > 0:
            horizontal = (w >= h)
            if horizontal:
                row_height = s / w
                cur_x = x
                for (rt, ra) in row:
                    rw = ra / row_height
                    rects.append(Rect(cur_x, y, rw, row_height, rt))
                    cur_x += rw
            else:
                row_width = s / h
                cur_y = y
                for (rt, ra) in row:
                    rh = ra / row_width
                    rects.append(Rect(x, cur_y, row_width, rh, rt))
                    cur_y += rh

    return rects

# ---------- Visualization generation ----------

def _truncate_text(text: str, max_length: int = 40) -> str:
    """Truncate text to max_length with ellipsis if needed."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."

def _get_font_size(rect_width: float, rect_height: float) -> int:
    """Determine appropriate font size based on rectangle dimensions."""
    min_dim = min(rect_width, rect_height)
    if min_dim < 30:
        return 6
    elif min_dim < 50:
        return 8
    elif min_dim < 80:
        return 10
    else:
        return 12

def generate_weekly_visualization(summary: Dict[str, Any], output_path: str, 
                                  width: int = 1200, height: int = 900) -> str:
    """
    Generate weekly visualization treemap image.
    
    Args:
        summary: Report summary dict from get_weekly_summary_with_sessions()
        output_path: Path to save the image
        width: Image width in pixels
        height: Image height in pixels
    
    Returns:
        Path to the generated image file
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        raise ImportError("matplotlib is required for visualization generation")
    
    # Convert summary to tasks
    tasks = create_tasks_from_summary(summary)
    
    if not tasks:
        # Create a simple "No data" image
        fig, ax = plt.subplots(figsize=(width/100, height/100), dpi=100)
        ax.text(0.5, 0.5, "No data available for this week", 
                ha="center", va="center", fontsize=16, transform=ax.transAxes)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        return output_path
    
    # Layout treemap
    rects = layout_treemap(tasks, width, height)
    
    if not rects:
        # Create a simple "No data" image
        fig, ax = plt.subplots(figsize=(width/100, height/100), dpi=100)
        ax.text(0.5, 0.5, "No data available for this week", 
                ha="center", va="center", fontsize=16, transform=ax.transAxes)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        return output_path
    
    # Create figure
    fig, ax = plt.subplots(figsize=(width/100, height/100), dpi=150)
    
    # Color palette for sessions (slightly varying shades)
    session_colors = ['#4A90E2', '#5BA3F5', '#6CB6FF', '#7DC7FF', '#8ED8FF']
    
    for r in rects:
        # Outer rectangle = promised time (border only)
        rect_patch = mpatches.Rectangle(
            (r.x, r.y), r.w, r.h,
            fill=False, 
            edgecolor='#333333',
            linewidth=1.5
        )
        ax.add_patch(rect_patch)
        
        # Inner stacked sessions (left -> right) showing filled time
        if r.task.promised > 0 and r.task.sessions and r.task.filled > 0:
            # Scale based on promised time (full width = promised)
            scale = r.w / r.task.promised
            cur_x = r.x
            total_rendered = 0.0
            
            for idx, s in enumerate(r.task.sessions):
                # Don't render more than filled time
                remaining_to_render = r.task.filled - total_rendered
                if remaining_to_render <= 0:
                    break
                
                # Use the session duration, but cap at remaining filled time
                dur = min(s.duration, remaining_to_render)
                if dur <= 0:
                    continue
                    
                w_sess = dur * scale
                
                # Use color from palette with slight variation
                color = session_colors[idx % len(session_colors)]
                alpha = 0.6 + 0.1 * (idx % 2)  # Vary alpha between 0.6 and 0.7
                
                session_patch = mpatches.Rectangle(
                    (cur_x, r.y),
                    w_sess, r.h,
                    facecolor=color,
                    alpha=alpha,
                    edgecolor='#222222',
                    linewidth=0.5
                )
                ax.add_patch(session_patch)
                
                cur_x += w_sess
                total_rendered += dur
        
        # Label in the center
        cx = r.x + r.w / 2
        cy = r.y + r.h / 2
        
        # Calculate progress
        progress = int((r.task.filled / r.task.promised * 100)) if r.task.promised > 0 else 0
        
        # Format text
        promise_text = _truncate_text(r.task.name, max_length=35)
        font_size = _get_font_size(r.w, r.h)
        
        # Only show text if rectangle is large enough
        if r.w > 40 and r.h > 30:
            label_text = f"{promise_text}\n{progress}% ({r.task.filled:.1f}/{r.task.promised:.1f}h)"
            ax.text(cx, cy, label_text,
                    ha="center", va="center", 
                    fontsize=font_size,
                    color='#000000',
                    weight='normal',
                    wrap=True)
        elif r.w > 20 and r.h > 15:
            # Minimal label for smaller rectangles
            label_text = f"{progress}%"
            ax.text(cx, cy, label_text,
                    ha="center", va="center", 
                    fontsize=min(font_size, 8),
                    color='#000000',
                    weight='normal')
    
    ax.set_xlim(0, width)
    ax.set_ylim(0, height)
    ax.set_aspect("equal")
    ax.invert_yaxis()
    ax.set_xticks([])
    ax.set_yticks([])
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    ax.spines['left'].set_visible(False)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white', pad_inches=0.1)
    plt.close()
    
    return output_path
