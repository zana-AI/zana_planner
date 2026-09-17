import type { PdfHighlight } from '../../types';

interface HighlightLayerProps {
  highlights: PdfHighlight[];
  pageIndex: number;
  onHighlightClick: (highlight: PdfHighlight) => void;
}

export function HighlightLayer({ highlights, pageIndex, onHighlightClick }: HighlightLayerProps) {
  return (
    <div className="pdf-reader-highlight-layer">
      {highlights
        .filter((highlight) => highlight.page_index === pageIndex)
        .flatMap((highlight) =>
          (highlight.rects_json || []).map((rect, rectIndex) => (
            <button
              key={`${highlight.id}-${rectIndex}`}
              type="button"
              className="pdf-reader-highlight-rect"
              aria-label={`Edit highlight: ${highlight.selected_text || 'selected text'}`}
              onClick={(event) => {
                event.stopPropagation();
                onHighlightClick(highlight);
              }}
              style={{
                left: `${rect.x * 100}%`,
                top: `${rect.y * 100}%`,
                width: `${rect.width * 100}%`,
                height: `${rect.height * 100}%`,
                backgroundColor: highlight.color || '#ffe066',
              }}
            />
          )),
        )}
    </div>
  );
}
