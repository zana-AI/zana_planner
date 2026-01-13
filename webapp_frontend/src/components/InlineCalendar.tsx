import { useState, useMemo } from 'react';

interface InlineCalendarProps {
  selectedDate?: string; // ISO date string (YYYY-MM-DD)
  onDateSelect: (date: string) => void; // Callback with ISO date string
  minDate?: string; // ISO date string - minimum selectable date
  onClose?: () => void;
}

const DAY_LABELS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];
const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

/**
 * InlineCalendar component - displays a month view calendar for date selection
 */
export function InlineCalendar({ selectedDate, onDateSelect, minDate, onClose }: InlineCalendarProps) {
  const today = useMemo(() => new Date(), []);
  const selectedDateObj = selectedDate ? new Date(selectedDate + 'T00:00:00') : null;
  const minDateObj = minDate ? new Date(minDate + 'T00:00:00') : null;
  
  const [currentMonth, setCurrentMonth] = useState(() => {
    if (selectedDateObj) {
      return new Date(selectedDateObj.getFullYear(), selectedDateObj.getMonth(), 1);
    }
    return new Date(today.getFullYear(), today.getMonth(), 1);
  });

  // Get first day of month and number of days
  const daysInMonth = new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 0).getDate();
  const startingDayOfWeek = new Date(currentMonth.getFullYear(), currentMonth.getMonth(), 1).getDay(); // 0 = Sunday, 1 = Monday, etc.

  // Generate calendar grid
  const calendarDays = useMemo(() => {
    const days: (Date | null)[] = [];
    
    // Add empty cells for days before the first day of the month
    for (let i = 0; i < startingDayOfWeek; i++) {
      days.push(null);
    }
    
    // Add all days of the month
    for (let day = 1; day <= daysInMonth; day++) {
      days.push(new Date(currentMonth.getFullYear(), currentMonth.getMonth(), day));
    }
    
    return days;
  }, [currentMonth, startingDayOfWeek, daysInMonth]);

  const handleDateClick = (date: Date) => {
    if (!date) return;
    
    // Check if date is before minDate
    if (minDateObj && date < minDateObj) {
      return;
    }
    
    // Format as YYYY-MM-DD
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const isoDate = `${year}-${month}-${day}`;
    
    onDateSelect(isoDate);
    if (onClose) {
      onClose();
    }
  };

  const handlePrevMonth = () => {
    setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 1));
  };

  const handleNextMonth = () => {
    setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1));
  };

  const isToday = (date: Date | null): boolean => {
    if (!date) return false;
    return (
      date.getDate() === today.getDate() &&
      date.getMonth() === today.getMonth() &&
      date.getFullYear() === today.getFullYear()
    );
  };

  const isSelected = (date: Date | null): boolean => {
    if (!date || !selectedDateObj) return false;
    return (
      date.getDate() === selectedDateObj.getDate() &&
      date.getMonth() === selectedDateObj.getMonth() &&
      date.getFullYear() === selectedDateObj.getFullYear()
    );
  };

  const isDisabled = (date: Date | null): boolean => {
    if (!date || !minDateObj) return false;
    return date < minDateObj;
  };

  const monthYear = `${MONTH_NAMES[currentMonth.getMonth()]} ${currentMonth.getFullYear()}`;

  return (
    <div className="inline-calendar" style={{
      backgroundColor: 'rgba(15, 23, 48, 0.8)',
      border: '1px solid rgba(232, 238, 252, 0.2)',
      borderRadius: '12px',
      padding: '16px',
      marginTop: '12px',
      width: '100%',
      maxWidth: '320px'
    }}>
      {/* Month/Year Header with Navigation */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: '16px'
      }}>
        <button
          onClick={handlePrevMonth}
          style={{
            background: 'rgba(232, 238, 252, 0.1)',
            border: '1px solid rgba(232, 238, 252, 0.2)',
            borderRadius: '6px',
            color: 'rgba(232, 238, 252, 0.9)',
            padding: '6px 12px',
            cursor: 'pointer',
            fontSize: '0.9rem',
            fontWeight: '600',
            transition: 'all 0.2s'
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'rgba(232, 238, 252, 0.2)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'rgba(232, 238, 252, 0.1)';
          }}
        >
          ←
        </button>
        <div style={{
          fontSize: '1rem',
          fontWeight: '700',
          color: '#fff'
        }}>
          {monthYear}
        </div>
        <button
          onClick={handleNextMonth}
          style={{
            background: 'rgba(232, 238, 252, 0.1)',
            border: '1px solid rgba(232, 238, 252, 0.2)',
            borderRadius: '6px',
            color: 'rgba(232, 238, 252, 0.9)',
            padding: '6px 12px',
            cursor: 'pointer',
            fontSize: '0.9rem',
            fontWeight: '600',
            transition: 'all 0.2s'
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'rgba(232, 238, 252, 0.2)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'rgba(232, 238, 252, 0.1)';
          }}
        >
          →
        </button>
      </div>

      {/* Day Labels */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(7, 1fr)',
        gap: '4px',
        marginBottom: '8px'
      }}>
        {DAY_LABELS.map((label, index) => (
          <div
            key={index}
            style={{
              textAlign: 'center',
              fontSize: '0.75rem',
              fontWeight: '600',
              color: 'rgba(232, 238, 252, 0.6)',
              padding: '4px'
            }}
          >
            {label}
          </div>
        ))}
      </div>

      {/* Calendar Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(7, 1fr)',
        gap: '4px'
      }}>
        {calendarDays.map((date, index) => {
          if (!date) {
            return <div key={index} />;
          }

          const isTodayDate = isToday(date);
          const isSelectedDate = isSelected(date);
          const isDisabledDate = isDisabled(date);

          return (
            <button
              key={index}
              onClick={() => handleDateClick(date)}
              disabled={isDisabledDate}
              style={{
                aspectRatio: '1',
                background: isSelectedDate
                  ? 'linear-gradient(135deg, #10b981, #059669)'
                  : isTodayDate
                  ? 'rgba(16, 185, 129, 0.2)'
                  : 'rgba(232, 238, 252, 0.05)',
                border: isSelectedDate
                  ? '2px solid #10b981'
                  : isTodayDate
                  ? '1px solid rgba(16, 185, 129, 0.4)'
                  : '1px solid rgba(232, 238, 252, 0.1)',
                borderRadius: '6px',
                color: isDisabledDate
                  ? 'rgba(232, 238, 252, 0.3)'
                  : isSelectedDate
                  ? '#fff'
                  : 'rgba(232, 238, 252, 0.9)',
                fontSize: '0.85rem',
                fontWeight: isSelectedDate || isTodayDate ? '600' : '400',
                cursor: isDisabledDate ? 'not-allowed' : 'pointer',
                transition: 'all 0.2s',
                padding: '0'
              }}
              onMouseEnter={(e) => {
                if (!isDisabledDate && !isSelectedDate) {
                  e.currentTarget.style.background = 'rgba(232, 238, 252, 0.15)';
                  e.currentTarget.style.borderColor = 'rgba(232, 238, 252, 0.3)';
                }
              }}
              onMouseLeave={(e) => {
                if (!isDisabledDate && !isSelectedDate) {
                  e.currentTarget.style.background = isTodayDate
                    ? 'rgba(16, 185, 129, 0.2)'
                    : 'rgba(232, 238, 252, 0.05)';
                  e.currentTarget.style.borderColor = isTodayDate
                    ? 'rgba(16, 185, 129, 0.4)'
                    : 'rgba(232, 238, 252, 0.1)';
                }
              }}
            >
              {date.getDate()}
            </button>
          );
        })}
      </div>
    </div>
  );
}
