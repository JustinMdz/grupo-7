# Encriptación Frontend — Grupo 4

Repositorio: https://github.com/JoseDanielJ/chat

---

## 1. Instalación

```bash
npx expo install tweetnacl tweetnacl-util react-native-get-random-values expo-secure-store
```

---

## 2. `utils/crypto.js` — CREAR
> Módulo con todas las funciones de cifrado y descifrado (DM y grupal). No existe aún en el proyecto.

```js
import 'react-native-get-random-values';
import nacl from 'tweetnacl';
import { encodeBase64, decodeBase64, encodeUTF8, decodeUTF8 } from 'tweetnacl-util';

export function generateKeyPair() {
  const kp = nacl.box.keyPair();
  return {
    publicKey: encodeBase64(kp.publicKey),
    secretKey: encodeBase64(kp.secretKey),
  };
}

export function encryptDM(message, recipientPublicKeyB64, mySecretKeyB64) {
  const nonce = nacl.randomBytes(nacl.box.nonceLength);
  const encrypted = nacl.box(
    encodeUTF8(message),
    nonce,
    decodeBase64(recipientPublicKeyB64),
    decodeBase64(mySecretKeyB64)
  );
  return encodeBase64(new Uint8Array([...nonce, ...encrypted]));
}

export function decryptDM(ciphertextB64, senderPublicKeyB64, mySecretKeyB64) {
  const data = decodeBase64(ciphertextB64);
  const nonce = data.slice(0, nacl.box.nonceLength);
  const box = data.slice(nacl.box.nonceLength);
  const result = nacl.box.open(box, nonce, decodeBase64(senderPublicKeyB64), decodeBase64(mySecretKeyB64));
  return result ? decodeUTF8(result) : null;
}

export function encryptGroup(message, groupKeyB64) {
  const nonce = nacl.randomBytes(nacl.secretbox.nonceLength);
  const encrypted = nacl.secretbox(encodeUTF8(message), nonce, decodeBase64(groupKeyB64));
  return encodeBase64(new Uint8Array([...nonce, ...encrypted]));
}

export function decryptGroup(ciphertextB64, groupKeyB64) {
  const data = decodeBase64(ciphertextB64);
  const nonce = data.slice(0, nacl.secretbox.nonceLength);
  const box = data.slice(nacl.secretbox.nonceLength);
  const result = nacl.secretbox.open(box, nonce, decodeBase64(groupKeyB64));
  return result ? decodeUTF8(result) : null;
}
```

---

## 3. `utils/storage.js` — CREAR
> Helpers para guardar y cargar el par de llaves usando `expo-secure-store` (almacenamiento cifrado del dispositivo). No existe aún en el proyecto. No usar AsyncStorage para esto — no está cifrado.

```js
import * as SecureStore from 'expo-secure-store';

export const saveKeyPair = async (kp) => {
  await SecureStore.setItemAsync('secretKey', kp.secretKey);
  await SecureStore.setItemAsync('publicKey', kp.publicKey);
};

export const loadKeyPair = async () => ({
  secretKey: await SecureStore.getItemAsync('secretKey'),
  publicKey: await SecureStore.getItemAsync('publicKey'),
});
```

---

## 4. `model/chat.types.ts` — MODIFICAR
> Agregar el campo `public_key` a la interfaz `ChatUser` para que el mapa de llaves públicas funcione con tipado correcto.

Buscar la interfaz `ChatUser` y agregar el campo:

```ts
public_key?: string | null;
```

---

## 5. `model/ws.types.ts` — MODIFICAR
> Agregar el evento `group_key` al tipo `WsEvent` para que TypeScript no marque error al procesarlo.

Buscar el tipo `WsEvent` (o el discriminated union de eventos) y agregar:

```ts
| { type: 'group_key'; key: string }
```

---

## 6. `service/chatService.ts` — MODIFICAR
> Agregar el método `registerPublicKey` para llamar al nuevo endpoint `PUT /api/chat/users/me/public-key`.

Agregar después del método `join`:

```ts
async registerPublicKey(token: string, publicKey: string): Promise<void> {
  await this.request<void>('/api/chat/users/me/public-key', {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({ public_key: publicKey }),
  });
}
```

---

## 7. `provider/chatContext.tsx` — MODIFICAR
> Archivo principal de estado y lógica del chat. Aquí se concentran todos los cambios restantes.

### 7.1 Imports a agregar

```ts
import { generateKeyPair, encryptGroup, decryptGroup, encryptDM, decryptDM } from '../utils/crypto';
import { saveKeyPair, loadKeyPair } from '../utils/storage';
```

### 7.2 Variables de estado a agregar

Junto a los demás `useState` del contexto:

```ts
const [groupKey, setGroupKey] = useState<string | null>(null);
const [userPublicKeys, setUserPublicKeys] = useState<Record<string, string>>({});
const [myKeyPair, setMyKeyPair] = useState<{ publicKey: string | null; secretKey: string | null }>({
  publicKey: null,
  secretKey: null,
});
```

### 7.3 Cargar el par de llaves al restaurar sesión

Dentro del `useEffect` de restauración de sesión (donde se lee AsyncStorage al montar), agregar:

```ts
const kp = await loadKeyPair();
if (kp.secretKey && kp.publicKey) {
  setMyKeyPair(kp);
}
```

### 7.4 Modificar `joinChat`

La función `joinChat` ya hace: join → guardar en AsyncStorage → conectar WS.

Agregar entre el join y la conexión WS:

```ts
// Cargar o generar par de llaves
let kp = await loadKeyPair();
if (!kp.secretKey || !kp.publicKey) {
  kp = generateKeyPair();
  await saveKeyPair(kp);
}
setMyKeyPair(kp);

// Registrar public key en el servidor — NUEVO (debe ir ANTES de conectar WS)
await ChatApiService.registerPublicKey(token, kp.publicKey);
```

### 7.5 Modificar el handler de eventos WebSocket

El handler existe donde se llama `wsRef.current.onEvent(...)`. Agregar o modificar los `case`:

```ts
case 'group_key':
  setGroupKey(event.key);
  // Si hay historial pendiente sin descifrar, descifrarlo aquí
  break;

case 'users_list':
  setUserPublicKeys(prev => {
    const updated = { ...prev };
    event.users.forEach(u => { if (u.public_key) updated[u.id] = u.public_key; });
    return updated;
  });
  setOnlineUsers(event.users);
  break;

case 'user_joined':
  if (event.user.public_key) {
    setUserPublicKeys(prev => ({ ...prev, [event.user.id]: event.user.public_key! }));
  }
  setOnlineUsers(prev => [...prev, event.user]);
  break;

case 'group_message': {
  const plaintext = groupKey ? decryptGroup(event.message.content, groupKey) : null;
  setGroupMessages(prev => [...prev, { ...event.message, content: plaintext ?? '[mensaje no descifrable]' }]);
  break;
}

case 'group_history': {
  // group_key llega DESPUÉS de group_history — descifrar cuando llegue group_key
  // Por ahora guardar cifrado; descifrar en el case 'group_key'
  setGroupMessages(event.messages); // se descifrarán cuando groupKey esté disponible
  break;
}

case 'dm': {
  const senderKey = userPublicKeys[event.message.sender_id];
  const plaintext = senderKey && myKeyPair.secretKey
    ? decryptDM(event.message.content, senderKey, myKeyPair.secretKey)
    : null;
  // Agregar a directMessages igual que hoy, pero con content descifrado
  const dmKey = event.message.sender_id === currentUser?.id
    ? event.message.recipient_id!
    : event.message.sender_id;
  setDirectMessages(prev => ({
    ...prev,
    [dmKey]: [...(prev[dmKey] ?? []), { ...event.message, content: plaintext ?? '[mensaje no descifrable]' }],
  }));
  break;
}
```

> **Nota sobre `group_history`:** el servidor envía `group_history` antes que `group_key`. El patrón recomendado es guardar los mensajes tal como llegan y en el `case 'group_key'` descifrar todos los mensajes del estado `groupMessages` en ese momento.

### 7.6 Modificar `sendGroupMessage`

La función ya llama a `wsRef.current.sendGroupMessage(content)`. Cifrar antes y validar longitud del ciphertext:

```ts
const sendGroupMessage = (content: string) => {
  if (!groupKey) return;
  const ciphertext = encryptGroup(content, groupKey);
  if (ciphertext.length > 1000) {
    // Mostrar error al usuario — el mensaje cifrado supera el límite del servidor
    Alert.alert('Mensaje demasiado largo', 'Acorta el mensaje e intenta de nuevo.');
    return;
  }
  wsRef.current?.sendGroupMessage(ciphertext);
};
```

> **Por qué 1000:** el ciphertext en Base64 es ~40% más largo que el texto original. El servidor de persistencia (Firebase) acepta hasta 1000 caracteres en el campo `content`. Un mensaje de ~700 caracteres de texto ya genera un ciphertext cercano a ese límite.

### 7.7 Modificar `sendDirectMessage`

La función ya llama a `wsRef.current.sendDM(userId, content)`. Cifrar antes y validar longitud del ciphertext:

```ts
const sendDirectMessage = (userId: string, content: string) => {
  const recipientKey = userPublicKeys[userId];
  if (!recipientKey || !myKeyPair.secretKey) return;
  const ciphertext = encryptDM(content, recipientKey, myKeyPair.secretKey);
  if (ciphertext.length > 1000) {
    Alert.alert('Mensaje demasiado largo', 'Acorta el mensaje e intenta de nuevo.');
    return;
  }
  wsRef.current?.sendDM(userId, ciphertext);
};
```

> **Nota:** la validación se hace sobre el ciphertext (no el texto plano) porque es lo que viaja al servidor. El usuario ve el texto original en pantalla — solo el servidor rechazaría el mensaje si fuera demasiado largo, así que la validación en frontend previene ese error antes de enviarlo.
