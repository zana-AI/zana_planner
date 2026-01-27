import { apiClient, ApiError } from '../../api/client';
import type { PromiseTemplate } from '../../types';
import { TemplateForm } from './TemplateForm';
import { DeleteConfirmModal } from './DeleteConfirmModal';

interface TemplatesTabProps {
  templates: PromiseTemplate[];
  loadingTemplates: boolean;
  editingTemplate: PromiseTemplate | null;
  showDeleteConfirm: string | null;
  deleteConfirmText: string;
  onSetEditingTemplate: (template: PromiseTemplate | null) => void;
  onSetShowDeleteConfirm: (id: string | null) => void;
  onSetDeleteConfirmText: (text: string) => void;
  onSetTemplates: (templates: PromiseTemplate[]) => void;
  onError: (error: string) => void;
}

export function TemplatesTab({
  templates,
  loadingTemplates,
  editingTemplate,
  showDeleteConfirm,
  deleteConfirmText,
  onSetEditingTemplate,
  onSetShowDeleteConfirm,
  onSetDeleteConfirmText,
  onSetTemplates,
  onError,
}: TemplatesTabProps) {
  if (loadingTemplates) {
    return (
      <div className="admin-panel-templates">
        <div className="admin-loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading templates...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-panel-templates">
      <div style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0, color: '#fff' }}>Promise Marketplace Templates</h2>
        <button
          onClick={() => onSetEditingTemplate({} as PromiseTemplate)}
          style={{
            padding: '0.5rem 1rem',
            background: 'linear-gradient(135deg, #667eea, #764ba2)',
            border: 'none',
            borderRadius: '6px',
            color: '#fff',
            cursor: 'pointer',
            fontSize: '0.9rem',
            fontWeight: '500'
          }}
        >
          + Create Template
        </button>
      </div>

      {editingTemplate !== null && (
        <TemplateForm
          template={editingTemplate}
          onSave={async (data) => {
            try {
              if (editingTemplate.template_id) {
                await apiClient.updateTemplate(editingTemplate.template_id, data);
              } else {
                await apiClient.createTemplate(data);
              }
              onSetEditingTemplate(null);
              // Refresh templates
              const response = await apiClient.getAdminTemplates();
              onSetTemplates(response.templates);
            } catch (err) {
              console.error('Failed to save template:', err);
              if (err instanceof ApiError) {
                onError(err.message);
              }
            }
          }}
          onCancel={() => onSetEditingTemplate(null)}
        />
      )}

      {showDeleteConfirm && (
        <DeleteConfirmModal
          templateId={showDeleteConfirm}
          templateTitle={templates.find(t => t.template_id === showDeleteConfirm)?.title || ''}
          onConfirm={async () => {
            try {
              await apiClient.deleteTemplate(showDeleteConfirm);
              onSetShowDeleteConfirm(null);
              onSetDeleteConfirmText('');
              // Refresh templates
              const response = await apiClient.getAdminTemplates();
              onSetTemplates(response.templates);
            } catch (err) {
              console.error('Failed to delete template:', err);
              if (err instanceof ApiError) {
                if (err.status === 409) {
                  // Try to parse error message for structured error details
                  try {
                    const errorData = JSON.parse(err.message);
                    if (errorData.message || errorData.reasons) {
                      onError(errorData.message || 'Template cannot be deleted: ' + (Array.isArray(errorData.reasons) ? errorData.reasons.join(', ') : 'Template is in use'));
                    } else {
                      onError(err.message);
                    }
                  } catch {
                    // If parsing fails, use the message as-is
                    onError(err.message || 'Template cannot be deleted because it is in use');
                  }
                } else {
                  onError(err.message);
                }
              } else {
                onError('Failed to delete template');
              }
              onSetShowDeleteConfirm(null);
              onSetDeleteConfirmText('');
            }
          }}
          onCancel={() => {
            onSetShowDeleteConfirm(null);
            onSetDeleteConfirmText('');
          }}
          confirmText={deleteConfirmText}
          onConfirmTextChange={onSetDeleteConfirmText}
        />
      )}

      <div style={{ display: 'grid', gap: '1rem' }}>
        {templates.map((template) => (
          <div
            key={template.template_id}
            style={{
              background: 'rgba(15, 23, 48, 0.6)',
              border: '1px solid rgba(232, 238, 252, 0.1)',
              borderRadius: '8px',
              padding: '1rem',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flex: 1 }}>
              <span style={{ fontSize: '1.5rem' }}>{template.emoji || '🎯'}</span>
              <div>
                <div style={{ fontSize: '1.05rem', fontWeight: '600', color: '#fff', marginBottom: '0.15rem' }}>
                  {template.title}
                </div>
                <div style={{ fontSize: '0.8rem', color: 'rgba(232, 238, 252, 0.5)' }}>
                  {template.target_value} {template.metric_type === 'hours' ? 'hrs' : '×'}/week • {template.category} • {template.is_active ? '✓ Active' : '○ Inactive'}
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                onClick={() => onSetEditingTemplate(template)}
                style={{
                  padding: '0.5rem 1rem',
                  background: 'rgba(91, 163, 245, 0.2)',
                  border: '1px solid rgba(91, 163, 245, 0.4)',
                  borderRadius: '6px',
                  color: '#5ba3f5',
                  cursor: 'pointer',
                  fontSize: '0.85rem'
                }}
              >
                Edit
              </button>
              <button
                onClick={() => onSetShowDeleteConfirm(template.template_id)}
                style={{
                  padding: '0.5rem 1rem',
                  background: 'rgba(255, 107, 107, 0.2)',
                  border: '1px solid rgba(255, 107, 107, 0.4)',
                  borderRadius: '6px',
                  color: '#ff6b6b',
                  cursor: 'pointer',
                  fontSize: '0.85rem'
                }}
              >
                Delete
              </button>
            </div>
          </div>
        ))}
        {templates.length === 0 && (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'rgba(232, 238, 252, 0.6)' }}>
            No templates found
          </div>
        )}
      </div>
    </div>
  );
}
