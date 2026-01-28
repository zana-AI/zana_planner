import { useRef, useEffect, useCallback } from 'react';
import './DurationWheelPicker.css';

interface DurationWheelPickerProps {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
}

export function DurationWheelPicker({ 
  value, 
  onChange, 
  min = 1, 
  max = 120 
}: DurationWheelPickerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const itemHeight = 44; // Height of each number item
  const visibleItems = 5; // Number of visible items (odd number for center selection)
  
  // Generate array of numbers
  const numbers = Array.from({ length: max - min + 1 }, (_, i) => min + i);
  
  // Scroll to the current value
  const scrollToValue = useCallback((val: number, smooth = false) => {
    if (!containerRef.current) return;
    const index = val - min;
    const scrollTop = index * itemHeight;
    containerRef.current.scrollTo({
      top: scrollTop,
      behavior: smooth ? 'smooth' : 'auto'
    });
  }, [min, itemHeight]);

  // Initialize scroll position
  useEffect(() => {
    // Small delay to ensure DOM is ready
    const timer = setTimeout(() => {
      scrollToValue(value, false);
    }, 50);
    return () => clearTimeout(timer);
  }, [scrollToValue, value]);

  // Handle scroll end - snap to nearest value
  const handleScroll = useCallback(() => {
    if (!containerRef.current) return;
    
    const container = containerRef.current;
    
    // Clear any existing timeout
    if ((container as any)._scrollTimeout) {
      clearTimeout((container as any)._scrollTimeout);
    }
    
    (container as any)._scrollTimeout = setTimeout(() => {
      const scrollTop = container.scrollTop;
      const index = Math.round(scrollTop / itemHeight);
      const newValue = Math.max(min, Math.min(max, min + index));
      
      // Snap to the value
      scrollToValue(newValue, true);
      
      if (newValue !== value) {
        onChange(newValue);
      }
    }, 100);
  }, [value, onChange, min, max, itemHeight, scrollToValue]);

  // Handle direct click on a number
  const handleItemClick = (num: number) => {
    scrollToValue(num, true);
    onChange(num);
  };

  return (
    <div className="wheel-picker-container">
      <div className="wheel-picker-highlight" />
      <div className="wheel-picker-fade-top" />
      <div className="wheel-picker-fade-bottom" />
      <div
        ref={containerRef}
        className="wheel-picker-scroll"
        onScroll={handleScroll}
        style={{
          height: itemHeight * visibleItems,
          paddingTop: itemHeight * Math.floor(visibleItems / 2),
          paddingBottom: itemHeight * Math.floor(visibleItems / 2),
        }}
      >
        {numbers.map((num) => (
          <div
            key={num}
            className={`wheel-picker-item ${num === value ? 'selected' : ''}`}
            style={{ height: itemHeight }}
            onClick={() => handleItemClick(num)}
          >
            {num}
          </div>
        ))}
      </div>
      <div className="wheel-picker-unit">minutes</div>
    </div>
  );
}
