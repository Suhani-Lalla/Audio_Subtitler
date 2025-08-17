# Video Subtitle Editor Frontend

A modern React frontend for the Video Subtitle Editor that communicates with the backend orchestrator to process videos and generate subtitles.

## Features

- **Video Upload**: Drag and drop or click to upload video files
- **Language Selection**: Choose from multiple target languages for subtitle translation
- **Real-time Preview**: See subtitle changes in real-time as you customize
- **Style Customization**: Customize font, color, position, and other subtitle properties
- **Download**: Download the final video with burned-in subtitles

## Prerequisites

- Node.js (v18 or higher)
- pnpm (recommended) or npm
- Backend orchestrator running on `http://localhost:8000`

## Installation

1. Install dependencies:

```bash
pnpm install
```

2. Start the development server:

```bash
pnpm dev
```

3. Open your browser and navigate to `http://localhost:5173`

## Backend Integration

This frontend is designed to work with the backend orchestrator (`orchestrator.py`). Make sure your backend is running on `http://localhost:8000` before using the frontend.

### API Endpoints

The frontend communicates with the following backend endpoints:

- `POST /process_initial` - Upload video and start processing
- `POST /overlay` - Apply subtitle overlay with customizations
- `GET /healthz` - Check backend health status

### Workflow

1. **Upload Video**: User uploads an MP4 video file
2. **Select Language**: User chooses target language for subtitle translation
3. **Process Initial**: Frontend calls `/process_initial` to extract audio and translate
4. **Customize Style**: User customizes subtitle appearance (font, color, position)
5. **Apply Overlay**: Frontend calls `/overlay` with job_id and style configuration
6. **Download**: User downloads the final video with burned-in subtitles

## Configuration

The API configuration is located in `src/config.js`. You can modify the `API_BASE_URL` if your backend is running on a different port or host.

## Development

- Built with React 19 and Vite
- Uses Tailwind CSS for styling
- Includes shadcn/ui components
- Supports hot module replacement for development

## Build for Production

```bash
pnpm build
```

The built files will be in the `dist` directory.

## Troubleshooting

- **Connection Error**: Make sure the backend orchestrator is running on `http://localhost:8000`
- **CORS Issues**: The backend should have CORS enabled for the frontend domain
- **File Upload Issues**: Ensure the video file is a supported format (MP4, MOV, etc.)
