import { useRef, useState } from 'react'

export const ACCEPTED_EXTENSIONS = '.pdf,.docx,.txt,.md'

interface Props {
  multiple?: boolean
  files: File[]
  onChange: (files: File[]) => void
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function FileDropzone({ multiple = false, files, onChange }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  function accept(list: FileList | null) {
    if (!list || list.length === 0) return
    const incoming = Array.from(list)
    onChange(multiple ? [...files, ...incoming] : incoming.slice(0, 1))
  }

  return (
    <div>
      <div
        className={dragging ? 'dropzone dropzone--active' : 'dropzone'}
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          accept(event.dataTransfer.files)
        }}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') inputRef.current?.click()
        }}
      >
        <strong>
          {multiple ? 'Drop resumes here' : 'Drop your resume here'} or click to browse
        </strong>
        <div className="dropzone__hint">PDF, DOCX, TXT or MD · up to 10 MB each</div>
        <input
          ref={inputRef}
          type="file"
          hidden
          multiple={multiple}
          accept={ACCEPTED_EXTENSIONS}
          onChange={(event) => {
            accept(event.target.files)
            // Reset so re-selecting the same file still fires onChange.
            event.target.value = ''
          }}
        />
      </div>

      {files.length > 0 && (
        <ul className="file-list">
          {files.map((file, index) => (
            <li key={`${file.name}-${index}`}>
              <span>{file.name}</span>
              <span className="file-list__size">{formatBytes(file.size)}</span>
              <button
                type="button"
                className="btn btn--ghost"
                style={{ padding: '0.1rem 0.5rem', fontSize: '0.8rem' }}
                onClick={() => onChange(files.filter((_, i) => i !== index))}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
