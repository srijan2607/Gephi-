'use client';

import FileUpload from '../components/FileUpload';

export default function Home() {
  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-white shadow-sm">
        <div className="max-w-3xl mx-auto px-4 py-6">
          <h1 className="text-2xl font-bold text-gray-900">
            Job Graph Converter
          </h1>
          <p className="mt-1 text-sm text-gray-600">
            Convert job dataset CSV to graph format for Gephi
          </p>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-3xl mx-auto px-4 py-8">
        <section className="bg-white rounded-lg shadow-sm p-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">
            Upload CSV File
          </h2>
          <FileUpload />
        </section>
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-gray-200 mt-12">
        <div className="max-w-3xl mx-auto px-4 py-6 text-center text-sm text-gray-500">
          Job Graph Converter - Server-side processing for large datasets
        </div>
      </footer>
    </div>
  );
}
