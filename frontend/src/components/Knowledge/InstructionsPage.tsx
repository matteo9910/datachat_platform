import React, { useState, useEffect, useCallback } from 'react';
import { instructionsApi, Instruction, CreateInstructionRequest, UpdateInstructionRequest } from '../../api/instructionsApi';
import { AxiosError } from 'axios';
import { Icons } from '../Layout/Icons';

// ---- Create/Edit Modal ----
interface InstructionModalProps {
  isOpen: boolean;
  instruction: Instruction | null; // null = create mode
  onClose: () => void;
  onSaved: () => void;
}

const InstructionModal: React.FC<InstructionModalProps> = ({ isOpen, instruction, onClose, onSaved }) => {
  const [type, setType] = useState<'global' | 'topic'>('global');
  const [topic, setTopic] = useState('');
  const [text, setText] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const isEdit = !!instruction;

  useEffect(() => {
    if (instruction) {
      setType(instruction.type);
      setTopic(instruction.topic || '');
      setText(instruction.text);
    } else {
      setType('global');
      setTopic('');
      setText('');
    }
    setError('');
  }, [instruction, isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim()) {
      setError('Instruction text is required');
      return;
    }
    if (type === 'topic' && !topic.trim()) {
      setError('Topic is required for topic-type instructions');
      return;
    }
    setError('');
    setSubmitting(true);
    try {
      if (isEdit && instruction) {
        const body: UpdateInstructionRequest = {
          type,
          topic: type === 'topic' ? topic.trim() : undefined,
          text: text.trim(),
        };
        await instructionsApi.updateInstruction(instruction.id, body);
      } else {
        const body: CreateInstructionRequest = {
          type,
          topic: type === 'topic' ? topic.trim() : undefined,
          text: text.trim(),
        };
        await instructionsApi.createInstruction(body);
      }
      onSaved();
      onClose();
    } catch (err: unknown) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setError(axiosErr?.response?.data?.detail || `Failed to ${isEdit ? 'update' : 'create'} instruction`);
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-2xl max-w-2xl w-full mx-4">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h3 className="text-sm font-black text-slate-900 uppercase tracking-widest">
            {isEdit ? 'Edit Instruction' : 'Add Instruction'}
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors p-1">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <div className="p-6">
          {error && <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">{error}</div>}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-bold text-slate-500 uppercase mb-1.5">Type</label>
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => setType('global')}
                  className={`flex-1 py-2.5 rounded-xl text-sm font-bold border transition-all ${
                    type === 'global'
                      ? 'bg-orange-600 text-white border-orange-600 shadow-lg shadow-orange-100'
                      : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300'
                  }`}
                >
                  Global
                </button>
                <button
                  type="button"
                  onClick={() => setType('topic')}
                  className={`flex-1 py-2.5 rounded-xl text-sm font-bold border transition-all ${
                    type === 'topic'
                      ? 'bg-blue-600 text-white border-blue-600 shadow-lg shadow-blue-100'
                      : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300'
                  }`}
                >
                  Per Topic
                </button>
              </div>
            </div>
            {type === 'topic' && (
              <div>
                <label className="block text-xs font-bold text-slate-500 uppercase mb-1.5">Topic Keyword</label>
                <input
                  value={topic}
                  onChange={e => setTopic(e.target.value)}
                  placeholder="e.g. vendite, revenue, inventory"
                  className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
                <p className="text-[10px] text-slate-400 mt-1">The instruction applies when the user&apos;s question contains this keyword</p>
              </div>
            )}
            <div>
              <label className="block text-xs font-bold text-slate-500 uppercase mb-1.5">Instruction Text</label>
              <textarea
                value={text}
                onChange={e => setText(e.target.value)}
                placeholder="e.g. Always use LIMIT 1000 for large tables"
                required
                rows={4}
                className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-orange-500 resize-y"
              />
            </div>
            <div className="flex gap-3 pt-2">
              <button type="button" onClick={onClose} className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm font-bold text-slate-600 hover:bg-slate-50 transition-all">
                Cancel
              </button>
              <button type="submit" disabled={submitting} className="flex-1 py-2.5 bg-orange-600 text-white rounded-xl text-sm font-bold hover:bg-orange-700 disabled:opacity-50 transition-all">
                {submitting ? (isEdit ? 'Saving...' : 'Creating...') : (isEdit ? 'Save Changes' : 'Create Instruction')}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};

// ---- Delete Confirmation Modal ----
interface DeleteModalProps {
  isOpen: boolean;
  instructionText: string;
  onClose: () => void;
  onConfirm: () => void;
}

const DeleteModal: React.FC<DeleteModalProps> = ({ isOpen, instructionText, onClose, onConfirm }) => {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-2xl max-w-sm w-full mx-4 overflow-hidden">
        <div className="p-6 text-center">
          <div className="w-14 h-14 bg-red-100 text-red-600 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
          </div>
          <h3 className="text-lg font-black text-slate-900 mb-2">Delete Instruction</h3>
          <p className="text-sm text-slate-500 mb-1">Are you sure you want to delete this instruction?</p>
          <p className="text-xs text-slate-400 mb-6 italic truncate px-4">&quot;{instructionText}&quot;</p>
          <div className="flex gap-3">
            <button onClick={onClose} className="flex-1 px-4 py-3 bg-slate-100 text-slate-700 rounded-xl text-sm font-bold hover:bg-slate-200 transition-colors">
              Cancel
            </button>
            <button onClick={() => { onConfirm(); onClose(); }} className="flex-1 px-4 py-3 bg-red-600 hover:bg-red-700 text-white rounded-xl text-sm font-bold transition-colors shadow-lg">
              Delete
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

// ---- Type Badge Component ----
const TypeBadge: React.FC<{ type: 'global' | 'topic'; topic?: string | null }> = ({ type, topic }) => {
  if (type === 'global') {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-orange-50 text-orange-700 rounded-lg text-[10px] font-bold uppercase tracking-widest">
        Global
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-blue-50 text-blue-700 rounded-lg text-[10px] font-bold uppercase tracking-widest">
      Topic: {topic}
    </span>
  );
};

// ---- Main Component ----
const InstructionsPage: React.FC = () => {
  const [instructions, setInstructions] = useState<Instruction[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editInstruction, setEditInstruction] = useState<Instruction | null>(null);
  const [deleteInstruction, setDeleteInstruction] = useState<Instruction | null>(null);

  const fetchInstructions = useCallback(async () => {
    setLoading(true);
    try {
      const data = await instructionsApi.getInstructions();
      setInstructions(data);
    } catch {
      // handled by interceptor
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchInstructions(); }, [fetchInstructions]);

  const handleDelete = async () => {
    if (!deleteInstruction) return;
    try {
      await instructionsApi.deleteInstruction(deleteInstruction.id);
      fetchInstructions();
    } catch {
      // handled by interceptor
    }
  };

  const filteredInstructions = instructions.filter(inst => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      inst.text.toLowerCase().includes(q) ||
      (inst.topic && inst.topic.toLowerCase().includes(q)) ||
      inst.type.toLowerCase().includes(q)
    );
  });

  return (
    <div className="p-8 h-full overflow-y-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Instructions</h1>
          <p className="text-xs text-slate-500 mt-1">Manage rules and guidelines injected into SQL generation prompts</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="px-4 py-2 bg-orange-600 text-white rounded-xl text-sm font-bold hover:bg-orange-700 transition-all shadow-lg shadow-orange-100 flex items-center gap-2"
        >
          <Icons.Plus /> Add Instruction
        </button>
      </div>

      {/* Search */}
      <div className="mb-6">
        <div className="relative max-w-md">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search instructions..."
            className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-orange-500"
          />
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12">
          <div className="w-8 h-8 border-4 border-orange-600 border-t-transparent rounded-full animate-spin mx-auto" />
        </div>
      ) : filteredInstructions.length === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center">
          <div className="w-16 h-16 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <Icons.FileText />
          </div>
          <h2 className="text-lg font-bold text-slate-700 mb-2">
            {search ? 'No matching instructions found' : 'No instructions yet'}
          </h2>
          <p className="text-sm text-slate-500 mb-6 max-w-md mx-auto">
            {search
              ? 'Try a different search term'
              : 'Instructions are rules injected into the AI\'s SQL generation prompt. Global instructions always apply; topic instructions activate when a user\'s question mentions the topic keyword.'}
          </p>
          {!search && (
            <button
              onClick={() => setShowCreateModal(true)}
              className="px-6 py-2.5 bg-orange-600 text-white rounded-xl text-sm font-bold hover:bg-orange-700 transition-all"
            >
              Add First Instruction
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <div className="text-xs text-slate-400 font-bold uppercase tracking-widest mb-2">
            {filteredInstructions.length} instruction{filteredInstructions.length !== 1 ? 's' : ''}{search ? ' found' : ''}
          </div>
          {filteredInstructions.map(inst => (
            <div key={inst.id} className="bg-white rounded-2xl border border-slate-200 p-5 hover:border-slate-300 transition-all group">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-2">
                    <TypeBadge type={inst.type} topic={inst.topic} />
                  </div>
                  <p className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">{inst.text}</p>
                  <div className="flex items-center gap-4 mt-3">
                    {inst.created_at && (
                      <span className="text-[10px] text-slate-400">
                        Created: {new Date(inst.created_at).toLocaleDateString()}
                      </span>
                    )}
                    {inst.updated_at && (
                      <span className="text-[10px] text-slate-400">
                        Updated: {new Date(inst.updated_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                  <button
                    onClick={() => setEditInstruction(inst)}
                    className="p-2 text-slate-400 hover:text-orange-600 hover:bg-orange-50 rounded-lg transition-all"
                    title="Edit instruction"
                  >
                    <Icons.Edit />
                  </button>
                  <button
                    onClick={() => setDeleteInstruction(inst)}
                    className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-all"
                    title="Delete instruction"
                  >
                    <Icons.Trash />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modals */}
      <InstructionModal
        isOpen={showCreateModal}
        instruction={null}
        onClose={() => setShowCreateModal(false)}
        onSaved={fetchInstructions}
      />
      <InstructionModal
        isOpen={!!editInstruction}
        instruction={editInstruction}
        onClose={() => setEditInstruction(null)}
        onSaved={fetchInstructions}
      />
      <DeleteModal
        isOpen={!!deleteInstruction}
        instructionText={deleteInstruction?.text || ''}
        onClose={() => setDeleteInstruction(null)}
        onConfirm={handleDelete}
      />
    </div>
  );
};

export default InstructionsPage;