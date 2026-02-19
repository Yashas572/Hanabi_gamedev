import pandas as pd
import numpy as np
import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import pickle

BATCH_SIZE = 256
EPOCHS = 50
LEARNING_RATE = 1e-4
MODEL_PATH = "hanabi_model.pt"
SCALER_PATH = "scaler.pkl"

class HanabiDataset(Dataset):
    def __init__(self, X, y):
        self.X = X
        self.y = y
    def __len__(self):
        return len(self.X)
    def __getitem__(self, idx):
        return (
            torch.tensor(self.X[idx], dtype=torch.float32),
            torch.tensor(self.y[idx], dtype=torch.long)
        )

class HanabiNet(nn.Module):
    def __init__(self, input_dim, hidden_dim=512, output_dim=20):
        super(HanabiNet, self).__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.BatchNorm1d(hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, hidden_dim),
            nn.BatchNorm1d(hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, output_dim)
        )
    def forward(self, x):
        return self.net(x)

def main():
    df = pd.read_csv("data/features.csv")
    action_columns = [
        "hint_green","hint_yellow","hint_white","hint_blue","hint_red",
        "hint_1","hint_2","hint_3","hint_4","hint_5",
        "play_1","play_2","play_3","play_4","play_5",
        "discard_1","discard_2","discard_3","discard_4","discard_5"
    ]
    df = df.dropna(subset=action_columns)
    input_columns = [c for c in df.columns if c not in action_columns]

    X = df[input_columns].values
    y_onehot = df[action_columns].values
    y = np.argmax(y_onehot, axis=1)

    row_sums = np.sum(y_onehot, axis=1)
    keep_mask = (row_sums == 1)
    X = X[keep_mask]
    y = y[keep_mask]

    unique, counts = np.unique(y, return_counts=True)
    print("Class distribution:", dict(zip(unique, counts)))

    freq_tensor = torch.tensor(counts, dtype=torch.float32)
    class_weights = 1.0 / freq_tensor
    class_weights = class_weights / class_weights.sum() * len(freq_tensor)

    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.1, random_state=42)

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled   = scaler.transform(X_val)

    with open(SCALER_PATH, "wb") as f:
        pickle.dump(scaler, f)

    train_ds = HanabiDataset(X_train_scaled, y_train)
    val_ds   = HanabiDataset(X_val_scaled, y_val)

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    val_loader   = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False)

    model = HanabiNet(input_dim=X.shape[1], hidden_dim=512, output_dim=20)
    criterion = nn.CrossEntropyLoss(weight=class_weights)
    optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)

    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', factor=0.5, patience=3, verbose=True
    )

    for epoch in range(EPOCHS):
        model.train()
        total_loss = 0
        for batch_X, batch_y in train_loader:
            optimizer.zero_grad()
            out = model(batch_X)
            loss = criterion(out, batch_y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * batch_X.size(0)
        train_loss = total_loss / len(train_ds)

        model.eval()
        val_loss = 0.0
        correct = 0
        total = 0
        with torch.no_grad():
            for batch_X, batch_y in val_loader:
                out = model(batch_X)
                loss = criterion(out, batch_y)
                val_loss += loss.item() * batch_X.size(0)
                _, pred = torch.max(out, 1)
                correct += (pred == batch_y).sum().item()
                total += batch_X.size(0)
        val_loss /= len(val_ds)
        val_acc = correct / total

        scheduler.step(val_loss)

        print(f"Epoch [{epoch+1}/{EPOCHS}] "
              f"Train Loss: {train_loss:.4f} "
              f"Val Loss: {val_loss:.4f} "
              f"Val Acc: {val_acc:.4f}")

    torch.save(model.state_dict(), MODEL_PATH)
    print("Done. Model saved.")

if __name__ == "__main__":
    main()
