#!/usr/bin/env python3
"""Add conversation viewer to AdminPanel.tsx"""

file_path = 'webapp_frontend/src/components/AdminPanel.tsx'

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line with createPromise closing
insert_pos = None
for i, line in enumerate(lines):
    if 'activeTab === \'createPromise\'' in line:
        # Find the closing of this section
        for j in range(i, len(lines)):
            if '})' in lines[j] and 'createPromise' not in lines[j]:
                insert_pos = j + 1
                break
        if insert_pos:
            break

if insert_pos is None:
    print("Could not find insertion point")
    exit(1)

# Conversation viewer section to insert
conversation_section = """      {activeTab === 'conversations' && (
        <ConversationViewer
          users={users}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          conversations={conversations}
          setConversations={setConversations}
          loadingConversations={loadingConversations}
          setLoadingConversations={setLoadingConversations}
          selectedConversationUserId={selectedConversationUserId}
          setSelectedConversationUserId={setSelectedConversationUserId}
          revealedMessageIds={revealedMessageIds}
          setRevealedMessageIds={setRevealedMessageIds}
          showAllUserMessages={showAllUserMessages}
          setShowAllUserMessages={setShowAllUserMessages}
        />
      )}
"""

# Insert the conversation section
lines.insert(insert_pos, conversation_section)

# Find where to add the component (before Dev Tool Link Component)
component_pos = None
for i, line in enumerate(lines):
    if '// Dev Tool Link Component' in line:
        component_pos = i
        break

if component_pos is None:
    print("Could not find component insertion point")
    exit(1)

# Read the component from a separate string
component_code = open('conversation_viewer_component.txt', 'r', encoding='utf-8').read()

# Insert component
lines.insert(component_pos, component_code)

# Write back
with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Successfully added conversation viewer")
