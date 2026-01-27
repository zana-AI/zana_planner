import { useState } from 'react';
import { apiClient } from '../../api/client';
import type { PromiseTemplate } from '../../types';
import { inputStyle, labelStyle } from './styles';

const EMOJI_OPTIONS = ['🏃', '📚', '💪', '🧘', '🎯', '✍️', '🎨', '🎵', '💻', '🌱', '💧', '😴', '🍎', '💰', '🧠', '❤️'];
const CATEGORY_OPTIONS = ['health', 'fitness', 'learning', 'productivity', 'mindfulness', 'creativity', 'finance', 'social', 'self-care', 'other'];

interface TemplateFormProps {
  template: Partial<PromiseTemplate>;
  onSave: (data: any) => void;
  onCancel: () => void;
}

export function TemplateForm({ template, onSave, onCancel }: TemplateFormProps) {
  const [prompt, setPrompt] = useState('');
  const [generating, setGenerating] = useState(false);
  const [formData, setFormData] = useState({
    title: template.title || '',
    description: template.description || '',
    category: template.category || 'other',
    target_value: template.target_value || 7,
    metric_type: template.metric_type || 'count',
    emoji: template.emoji || '',
    is_active: template.is_active !== undefined ? (typeof template.is_active === 'number' ? template.is_active !== 0 : template.is_active) : true,
  });

  const handleGenerate = async () => {
    if (!prompt.trim()) return;
    setGenerating(true);
    try {
      const draft = await apiClient.generateTemplateDraft(prompt);
      setFormData({
        title: draft.title || '',
        description: draft.description || '',
        category: draft.category || 'other',
        target_value: draft.target_value || 7,
        metric_type: draft.metric_type || 'count',
        emoji: draft.emoji || '',
        is_active: true,
      });
    } catch (err) {
      console.error('Failed to generate template:', err);
      alert('Failed to generate template. Please try again.');
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div style={{
      background: 'rgba(15, 23, 48, 0.9)',
      border: '1px solid rgba(232, 238, 252, 0.15)',
      borderRadius: '16px',
      padding: '1.5rem',
      marginBottom: '1.5rem'
    }}>
      <h3 style={{ marginTop: 0, marginBottom: '1.25rem', color: '#fff', fontSize: '1.2rem' }}>
        {template.template_id ? '✏️ Edit Template' : '✨ Create Template'}
      </h3>

      {/* AI Generation Section */}
      {!template.template_id && (
        <div style={{
          marginBottom: '1.5rem',
          padding: '1rem',
          background: 'linear-gradient(135deg, rgba(91, 163, 245, 0.1), rgba(118, 75, 162, 0.1))',
          borderRadius: '12px',
          border: '1px solid rgba(91, 163, 245, 0.2)'
        }}>
          <label style={{ ...labelStyle, color: '#5ba3f5' }}>
            🤖 Quick Create with AI
          </label>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <input
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g., Exercise 3 times a week"
              onKeyPress={(e) => e.key === 'Enter' && handleGenerate()}
              style={{ ...inputStyle, flex: 1 }}
            />
            <button
              onClick={handleGenerate}
              disabled={!prompt.trim() || generating}
              style={{
                padding: '0.75rem 1.25rem',
                background: generating ? 'rgba(91, 163, 245, 0.3)' : 'linear-gradient(135deg, #5ba3f5, #667eea)',
                border: 'none',
                borderRadius: '8px',
                color: '#fff',
                cursor: (!prompt.trim() || generating) ? 'not-allowed' : 'pointer',
                opacity: (!prompt.trim() || generating) ? 0.6 : 1,
                fontWeight: '600',
                whiteSpace: 'nowrap'
              }}
            >
              {generating ? '...' : 'Generate'}
            </button>
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gap: '1.25rem' }}>
        {/* Title + Emoji Row */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '1rem', alignItems: 'end' }}>
          <div>
            <label style={labelStyle}>Title *</label>
            <input
              type="text"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              placeholder="e.g., Daily Exercise"
              style={inputStyle}
            />
          </div>
          <div>
            <label style={labelStyle}>Emoji</label>
            <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', maxWidth: '200px' }}>
              {EMOJI_OPTIONS.map(emoji => (
                <button
                  key={emoji}
                  onClick={() => setFormData({ ...formData, emoji: formData.emoji === emoji ? '' : emoji })}
                  style={{
                    width: '32px',
                    height: '32px',
                    border: formData.emoji === emoji ? '2px solid #5ba3f5' : '1px solid rgba(232, 238, 252, 0.15)',
                    borderRadius: '6px',
                    background: formData.emoji === emoji ? 'rgba(91, 163, 245, 0.2)' : 'rgba(11, 16, 32, 0.6)',
                    cursor: 'pointer',
                    fontSize: '1rem'
                  }}
                >
                  {emoji}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Description */}
        <div>
          <label style={labelStyle}>Description (optional)</label>
          <textarea
            value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
            rows={2}
            placeholder="Why is this habit valuable?"
            style={{ ...inputStyle, resize: 'vertical' }}
          />
        </div>

        {/* Category + Target Row */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem' }}>
          <div>
            <label style={labelStyle}>Category</label>
            <select
              value={formData.category}
              onChange={(e) => setFormData({ ...formData, category: e.target.value })}
              style={inputStyle}
            >
              {CATEGORY_OPTIONS.map(cat => (
                <option key={cat} value={cat}>{cat.charAt(0).toUpperCase() + cat.slice(1)}</option>
              ))}
            </select>
          </div>
          <div>
            <label style={labelStyle}>Target</label>
            <input
              type="number"
              step="1"
              min="1"
              value={formData.target_value}
              onChange={(e) => setFormData({ ...formData, target_value: parseFloat(e.target.value) || 1 })}
              style={inputStyle}
            />
          </div>
          <div>
            <label style={labelStyle}>Per Week</label>
            <select
              value={formData.metric_type}
              onChange={(e) => setFormData({ ...formData, metric_type: e.target.value as 'hours' | 'count' })}
              style={inputStyle}
            >
              <option value="count">times</option>
              <option value="hours">hours</option>
            </select>
          </div>
        </div>

        {/* Preview */}
        <div style={{
          padding: '1rem',
          background: 'rgba(0,0,0,0.2)',
          borderRadius: '10px',
          border: '1px dashed rgba(232, 238, 252, 0.1)'
        }}>
          <div style={{ fontSize: '0.8rem', color: 'rgba(232, 238, 252, 0.5)', marginBottom: '0.5rem' }}>Preview</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{ fontSize: '1.5rem' }}>{formData.emoji || '🎯'}</span>
            <div>
              <div style={{ fontWeight: '600', color: '#fff' }}>{formData.title || 'Template Title'}</div>
              <div style={{ fontSize: '0.85rem', color: 'rgba(232, 238, 252, 0.6)' }}>
                {formData.target_value} {formData.metric_type === 'hours' ? 'hours' : 'times'}/week • {formData.category}
              </div>
            </div>
          </div>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', paddingTop: '0.5rem' }}>
          <button
            onClick={onCancel}
            style={{
              padding: '0.75rem 1.5rem',
              background: 'transparent',
              border: '1px solid rgba(232, 238, 252, 0.2)',
              borderRadius: '8px',
              color: 'rgba(232, 238, 252, 0.8)',
              cursor: 'pointer',
              fontSize: '0.95rem'
            }}
          >
            Cancel
          </button>
          <button
            onClick={() => onSave(formData)}
            disabled={!formData.title.trim()}
            style={{
              padding: '0.75rem 1.5rem',
              background: !formData.title.trim() ? 'rgba(102, 126, 234, 0.3)' : 'linear-gradient(135deg, #667eea, #764ba2)',
              border: 'none',
              borderRadius: '8px',
              color: '#fff',
              cursor: !formData.title.trim() ? 'not-allowed' : 'pointer',
              fontSize: '0.95rem',
              fontWeight: '600'
            }}
          >
            {template.template_id ? 'Save Changes' : 'Create Template'}
          </button>
        </div>
      </div>
    </div>
  );
}
