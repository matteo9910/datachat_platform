import React from 'react';

const KnowledgeBase: React.FC = () => {
  return (
    <div className="p-8">
      <h1 className="text-xl font-bold text-slate-900 mb-4">Knowledge Base</h1>
      <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center">
        <div className="text-4xl mb-4">ð</div>
        <h2 className="text-lg font-bold text-slate-700 mb-2">Knowledge Base</h2>
        <p className="text-sm text-slate-500">
          Manage question-SQL pairs to progressively train the AI system.
          This feature is coming soon.
        </p>
      </div>
    </div>
  );
};

export default KnowledgeBase;
