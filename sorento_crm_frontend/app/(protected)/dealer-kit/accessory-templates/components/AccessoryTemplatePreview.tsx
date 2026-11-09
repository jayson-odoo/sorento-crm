import { accessoryBoxLayout } from '@/lib/dealer-kit/accessory-box';
import { cardBoxLayout } from '@/lib/dealer-kit/accessory-card';
import { defaultAccessoriesProps, type AccessoriesLayerProps } from '@/lib/dealer-kit/tag-template-types';
import type { AccessoryDesign } from '@/lib/dealer-kit/accessory-card';

const BOX = { w: 60, h: 80 };
const SAMPLE_CARDS = 2;
const PT_TO_MM = 0.3528;

/** A small static drawing of a saved design: frame, header text and the cards' outlines. */
export function AccessoryTemplatePreview({ design }: { design: AccessoryDesign }) {
  const props = { ...defaultAccessoriesProps(), ...design, kind: 'accessories' } as AccessoriesLayerProps;
  const box = props.card
    ? cardBoxLayout(SAMPLE_CARDS, props, BOX.w, BOX.h)
    : accessoryBoxLayout(SAMPLE_CARDS, props, BOX.w, BOX.h);
  const scale = 'scale' in box ? (box as { scale: number }).scale : 1;
  const w = box.boxWidth_mm || BOX.w;
  const h = box.boxHeight_mm || BOX.h;
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      className="h-12 w-auto max-w-full"
      role="img"
      aria-label="Preview"
    >
      {box.frame && (
        <rect
          x={box.frame.x_mm}
          y={box.frame.y_mm}
          width={box.frame.width_mm}
          height={box.frame.height_mm}
          fill={props.fill}
          stroke={props.stroke}
          strokeWidth={props.strokeWidth_mm}
          rx={props.cornerRadius_mm}
        />
      )}
      {box.header?.fill && (
        <rect
          x={box.header.x_mm}
          y={box.header.y_mm}
          width={box.header.width_mm}
          height={box.header.height_mm}
          rx={box.header.radius_mm}
          fill={box.header.fill}
        />
      )}
      {box.header && (
        <text
          x={box.header.x_mm + box.header.width_mm / 2}
          y={box.header.y_mm + box.header.height_mm * 0.75}
          textAnchor="middle"
          fontSize={box.header.fontSize_pt * PT_TO_MM}
          fontWeight={700}
          fill={props.headerColor}
        >
          {props.headerText}
        </text>
      )}
      {box.cards.map((card, i) => (
        <g key={i}>
          <rect
            x={card.x_mm}
            y={card.y_mm}
            width={card.width_mm}
            height={card.height_mm}
            fill={props.cardFill}
            stroke="#d1d5db"
            strokeWidth={0.3}
          />
          {(props.card?.elements ?? [])
            .filter((el) => !el.hidden)
            .map((el) => (
              <rect
                key={el.id}
                x={card.x_mm + el.x_mm * scale}
                y={card.y_mm + el.y_mm * scale}
                width={el.width_mm * scale}
                height={Math.max(el.height_mm * scale, 0.4)}
                fill={el.kind === 'picture' ? '#e5e7eb' : el.kind === 'colour_dots' ? '#9ca3af' : '#6b7280'}
                opacity={el.kind === 'text' ? 0.5 : 0.8}
              />
            ))}
        </g>
      ))}
    </svg>
  );
}
