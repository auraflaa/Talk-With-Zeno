import React, { useEffect, useState } from 'react';
import { apiService, Personalization } from '../services/apiService';

interface SettingsModalProps {
  userId: string;
  userName: string;
  isOpen: boolean;
  onClose: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  userId,
  userName,
  isOpen,
  onClose,
}) => {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [aboutMe, setAboutMe] = useState('');
  const [formality, setFormality] = useState<'casual' | 'semi-formal' | 'formal'>('casual');
  const [messageLength, setMessageLength] = useState<'very_short' | 'short' | 'medium' | 'long'>('short');
  const [punctuationStyle, setPunctuationStyle] = useState<'minimal' | 'some' | 'full'>('minimal');
  const [languageStyle, setLanguageStyle] = useState<'texting' | 'conversational' | 'formal'>('conversational');
  const [rawPersonalization, setRawPersonalization] = useState<Personalization | null>(null);
  const [notesDraft, setNotesDraft] = useState<any[] | null>(null);
  const [activeTab, setActiveTab] = useState<'profile' | 'notes'>('profile');

  const buildNotes = (notesSource: any[] | null | undefined): { text: string; timestamp?: string }[] => {
    if (!notesSource || !Array.isArray(notesSource)) return [];
    const list: { text: string; timestamp?: string }[] = [];

    if (notesSource.length > 0) {
      const recentNotes = notesSource.slice(-6); // show up to 6 most recent notes
      recentNotes.forEach((n: any) => {
        if (typeof n === 'string') {
          list.push({ text: n });
        } else if (n && typeof n.text === 'string') {
          list.push({ text: n.text, timestamp: n.timestamp });
        } else {
          list.push({ text: JSON.stringify(n) });
        }
      });
    }

    return list;
  };

  const noteEntries = buildNotes(notesDraft ?? rawPersonalization?.notes);

  const handleDeleteNote = async (index: number) => {
    // Mark note as deleted in local draft; actual delete happens on Save
    const source = notesDraft ?? rawPersonalization?.notes ?? [];
    const currentNotes = Array.isArray(source) ? [...source] : [];
    if (index < 0 || index >= currentNotes.length) return;
    currentNotes.splice(index, 1);
    setNotesDraft(currentNotes);
    setSuccess('Note marked for deletion. Click "Save settings" to apply.');
  };

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    setError(null);
    setSuccess(null);

    apiService
      .getPersonalization(userId)
      .then((data: Personalization) => {
        setRawPersonalization(data);
        setNotesDraft(data.notes || []);
        const prefs = data.preferences || {};
        const comm = prefs.communication_style || {};
        const meta = (data.metadata as any) || {};

        if (meta.about_me && typeof meta.about_me === 'string') {
          setAboutMe(meta.about_me);
        } else {
          setAboutMe('');
        }

        if (comm.formality && ['casual', 'semi-formal', 'formal'].includes(comm.formality)) {
          setFormality(comm.formality as any);
        }
        if (comm.message_length && ['very_short', 'short', 'medium', 'long'].includes(comm.message_length)) {
          setMessageLength(comm.message_length as any);
        }
        if (comm.punctuation_style && ['minimal', 'some', 'full'].includes(comm.punctuation_style)) {
          setPunctuationStyle(comm.punctuation_style as any);
        }
        if (comm.language_style && ['texting', 'conversational', 'formal'].includes(comm.language_style)) {
          setLanguageStyle(comm.language_style as any);
        }
      })
      .catch((err) => {
        console.error('Failed to load personalization', err);
        setError('Failed to load your settings. Please try again.');
      })
      .finally(() => setLoading(false));
  }, [isOpen, userId]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const personalizationUpdate: Partial<Personalization> = {
        metadata: {
          about_me: aboutMe,
        },
        preferences: {
          communication_style: {
            formality,
            message_length: messageLength,
            punctuation_style: punctuationStyle,
            language_style: languageStyle,
          },
        },
      };

      // If notesDraft is set, persist it (including deletions)
      if (notesDraft) {
        (personalizationUpdate as any).notes = notesDraft;
      }

      const updated = await apiService.updatePersonalization(userId, personalizationUpdate);
      setRawPersonalization(updated);
      setNotesDraft(updated.notes || []);
      setSuccess('Settings saved. Zeno will use this info in future conversations.');
    } catch (err: any) {
      console.error('Failed to save personalization', err);
      setError(err?.message || 'Failed to save settings. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative z-10 bg-base-100 rounded-2xl shadow-2xl p-6 w-full max-w-xl border border-base-200">
        <h2 className="text-xl font-semibold mb-1 text-base-content">Settings</h2>
        <p className="text-sm text-base-content mb-3">
          Tell Zeno about yourself and how you like to talk. This updates the personalization data the model uses on every turn.
        </p>

        {/* Tabs */}
        <div className="mb-4 flex gap-2 border-b border-base-200 text-sm">
          <button
            type="button"
            onClick={() => setActiveTab('profile')}
            className={`px-3 py-1 -mb-px border-b-2 transition-colors ${
              activeTab === 'profile'
                ? 'border-primary text-primary font-medium'
                : 'border-transparent text-base-content/70 hover:text-base-content'
            }`}
          >
            Profile
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('notes')}
            className={`px-3 py-1 -mb-px border-b-2 transition-colors ${
              activeTab === 'notes'
                ? 'border-primary text-primary font-medium'
                : 'border-transparent text-base-content/70 hover:text-base-content'
            }`}
          >
            Saved notes
          </button>
        </div>

        {loading ? (
          <div className="py-8 text-center text-base-content/70 text-sm">Loading your settings…</div>
        ) : (
          <>
            {activeTab === 'profile' && (
              <>
                {/* About Me */}
                <div className="mb-5">
                  <label className="block text-sm font-semibold text-base-content mb-1">
                    About you
                  </label>
                  <textarea
                    className="textarea textarea-bordered w-full h-24 text-sm 
                               bg-[#FFF7ED] text-black placeholder:text-black/50
                               dark:bg-[#1F2933] dark:text-[#F9FAFB] dark:placeholder:text-[#F9FAFB]/60"
                    placeholder={`E.g. "I'm ${userName}, I love tech, late-night chats, and honest conversations."`}
                    value={aboutMe}
                    onChange={(e) => setAboutMe(e.target.value)}
                  />
                  <p className="mt-1 text-xs text-base-content">
                    A short bio Zeno can use for context (not shared with anyone else).
                  </p>
                </div>

                {/* Communication style */}
                <div className="mb-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-semibold text-base-content mb-1">
                      Formality
                    </label>
                    <select
                      className="select select-bordered w-full select-sm 
                                 bg-[#FFF7ED] text-black
                                 dark:bg-[#1F2933] dark:text-[#F9FAFB]"
                      value={formality}
                      onChange={(e) => setFormality(e.target.value as any)}
                    >
                      <option value="casual">Casual</option>
                      <option value="semi-formal">Semi-formal</option>
                      <option value="formal">Formal</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-base-content mb-1">
                      Message length
                    </label>
                    <select
                      className="select select-bordered w-full select-sm 
                                 bg-[#FFF7ED] text-black
                                 dark:bg-[#1F2933] dark:text-[#F9FAFB]"
                      value={messageLength}
                      onChange={(e) => setMessageLength(e.target.value as any)}
                    >
                      <option value="very_short">Very short (1–5 words)</option>
                      <option value="short">Short (1 sentence)</option>
                      <option value="medium">Medium (2–3 sentences)</option>
                      <option value="long">Long (paragraphs)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-base-content mb-1">
                      Punctuation style
                    </label>
                    <select
                      className="select select-bordered w-full select-sm 
                                 bg-[#FFF7ED] text-black
                                 dark:bg-[#1F2933] dark:text-[#F9FAFB]"
                      value={punctuationStyle}
                      onChange={(e) => setPunctuationStyle(e.target.value as any)}
                    >
                      <option value="minimal">Minimal</option>
                      <option value="some">Some</option>
                      <option value="full">Full</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-base-content mb-1">
                      Language style
                    </label>
                    <select
                      className="select select-bordered w-full select-sm 
                                 bg-[#FFF7ED] text-black
                                 dark:bg-[#1F2933] dark:text-[#F9FAFB]"
                      value={languageStyle}
                      onChange={(e) => setLanguageStyle(e.target.value as any)}
                    >
                      <option value="texting">Texting (u, ur, yeah)</option>
                      <option value="conversational">Conversational (you, your, yes)</option>
                      <option value="formal">Formal (proper grammar)</option>
                    </select>
                  </div>
                </div>
              </>
            )}

            {activeTab === 'notes' && rawPersonalization && (
              <div className="mt-1">
                {noteEntries.length === 0 ? (
                  <p className="text-xs text-base-content/60">
                    Zeno hasn’t saved any notes about you yet.
                  </p>
                ) : (
                  <div className="space-y-2 max-h-64 overflow-auto pr-1">
                    {noteEntries.map((entry, idx) => (
                      <div
                        key={idx}
                        className="rounded-lg bg-[#FFF7ED] text-black px-3 py-2 text-xs flex items-start justify-between gap-3
                                   dark:bg-[#1F2933] dark:text-[#E5E7EB]"
                      >
                        <div>
                          <p className="leading-snug">{entry.text}</p>
                          {entry.timestamp && (
                            <p className="mt-1 text-[10px] text-black/60 dark:text-[#9CA3AF]">
                              {new Date(entry.timestamp).toLocaleString()}
                            </p>
                          )}
                        </div>
                        <button
                          type="button"
                          className="text-[11px] text-error hover:underline whitespace-nowrap ml-1"
                          onClick={() => handleDeleteNote(idx)}
                        >
                          Delete
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {error && (
              <div className="mt-3 text-xs text-error">
                {error}
              </div>
            )}
            {success && (
              <div className="mt-3 text-xs text-success">
                {success}
              </div>
            )}

            <div className="mt-4 flex justify-end gap-3">
              <button
                className="btn btn-ghost btn-sm"
                onClick={onClose}
                disabled={saving}
              >
                Close
              </button>
              <button
                className="btn btn-sm bg-primary hover:bg-primary-hover text-white border-none"
                onClick={() => {
                  if (saving || activeTab === 'notes') return;
                  handleSave();
                }}
              >
                {saving ? 'Saving…' : 'Save settings'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};


