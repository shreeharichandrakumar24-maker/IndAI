// Loads the shared alias/preset map (single source of truth also read by
// Jarvis in Python) and injects it into the ui.command validator once at
// startup. Kept separate from uiCommand.js so that module stays importable
// in plain Node (no JSON import attributes needed in unit tests).
import data from '../../../shared/navigation.json';
import { setNavigationData } from '../components/voice/uiCommand.js';

setNavigationData(data);

export default data;
