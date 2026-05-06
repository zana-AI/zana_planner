import type { PdfHighlight } from '../../types';

interface HighlightLayerProps {
  highlights: PdfHighlight[];
  pageIndex: number;
}

export function HighlightLayer({ highlights, pageIndex }: HighlightLayerProps) {
  return (
    <div className="pdf-reader-highlight-layer" aria-hidden="true">
      {highlights
        .filter((highlight) => highlight.page_index === pageIndex)
        .flatMap((highlight) =>
          (highlight.rects_json || []).map((rect, rectIndex) => (
            <div
              key={`${highlight.id}-${rectIndex}`}
              className="pdf-reader-highlight-rect"
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
