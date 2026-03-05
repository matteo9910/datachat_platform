import React from 'react';

const Instructions: React.FC = () => {
  return (
    <div className="p-8">
      <h1 className="text-xl font-bold text-slate-900 mb-4">Instructions</h1>
      <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center">
        <div className="text-4xl mb-4">ð</div>
        <h2 className="text-lg font-bold text-slate-700 mb-2">System Instructions</h2>
        <p className="text-sm text-slate-500">
          Configure global and per-topic instructions to guide SQL generation.
          This feature is coming soon.
        </p>
      </div>
    </div>
  );
};

export default Instructions;
