import random, json
import pyxel

from key_map import KEY_MAP

with open("mp.config", "r+") as f:
    mpconfig = json.loads(f.read())

pixon_state = 0 if mpconfig["inverse"] else 7
pixoff_state = 7 if mpconfig["inverse"] else 0

clock_speed = mpconfig["clock_speed"]
allow_logging = mpconfig["allow_logging"]

class CPU:
    #opcodes

    def _0ZZZ(self):
        #0x00E0 conflicts with 0x00EE, must extract again here
        extracted_op = self.opcode & 0xf0ff
        try:
            self.funcmap[extracted_op]()
        except:
            if allow_logging:
                with open("log.txt", "a") as f:
                    f.write(f"Unknown Instruction (at _0ZZZ): {hex(extracted_op)}\n")

    def _0ZZ0(self): 
        #clear the screen
        self.display_buffer = [0]*64*32 # 64*32
        self.should_draw = True

    def _0ZZE(self):
        #return from subroutine
        self.pc = self.stack.pop()

    def _1ZZZ(self):
        #jumps to address NNN
        self.pc = self.opcode & 0x0fff

    def _2ZZZ(self):
        #call subroutine at NNN
        self.stack.append(self.pc)
        self.pc = self.opcode & 0x0fff
    
    def _3ZZZ(self):
        #skip next instr if vx == kk
        if self.gpio[self.vx] == (self.opcode & 0x00ff):
            self.pc += 2

    def _4ZZZ(self):
        #skip next instr if vx != kk
        if self.gpio[self.vx] != (self.opcode & 0x00ff):
            self.pc += 2
    
    def _5ZZZ(self):
        #skip next instr if vx == vy
        if self.gpio[self.vx] == self.gpio[self.vy]:
            self.pc += 2
    
    def _6ZZZ(self):
        #set vx to kk
        self.gpio[self.vx] = (self.opcode & 0x00ff)
    
    def _7ZZZ(self):
        #add vx to kk and set result as vx
        self.gpio[self.vx] += (self.opcode & 0xff)

    def _8ZZZ(self):
        #another conflict, extract again here
        extracted_op = self.opcode & 0xf00f
        extracted_op += 0xff0

        try:
            self.funcmap[extracted_op]()
        except:
            if allow_logging:
                with open("log.txt", "a") as f:
                    f.write(f"Unknown Instruction (at _8ZZZ): {hex(extracted_op)}\n")
    
    def _8ZZ0(self):
        #set vx to vy
        self.gpio[self.vx] = self.gpio[self.vy]
        self.gpio[self.vx] &= 0xff

    def _8ZZ1(self):
        #set vx to vx or vy
        self.gpio[self.vx] |= self.gpio[self.vy]
        self.gpio[self.vx] &= 0xff

    def _8ZZ2(self):
        #set vx to vx and vy
        self.gpio[self.vx] &= self.gpio[self.vy]
        self.gpio[self.vx] &= 0xff

    def _8ZZ3(self):
        #set vx to vx xor vy
        self.gpio[self.vx] ^= self.gpio[self.vy]
        self.gpio[self.vx] &= 0xff

    def _8ZZ4(self):
        #set vx to vx + vy, set vf to carry
        
        if self.gpio[self.vx] + self.gpio[self.vy] > 0xff:
            self.gpio[0xf] = 1
        else:
            self.gpio[0xf] = 0
        self.gpio[self.vx] += self.gpio[self.vy]
        self.gpio[self.vx] &= 0xff

    def _8ZZ5(self):
        #set vx to vx - vy, set vf to NOT borrow
        if self.gpio[self.vx] > self.gpio[self.vy]:
            self.gpio[0xf] = 1
        else:
            self.gpio[0xf] = 0
        self.gpio[self.vx] -= self.gpio[self.vy]
        self.gpio[self.vx] &= 0xff

    def _8ZZ6(self):
        #shift vx right 1
        self.gpio[0xf] = self.gpio[self.vx] & 0x0001 #if least significant bit of vx is 1, set vf to 1
        self.gpio[self.vx] >>= 1

    def _8ZZ7(self):
        #same as 8xy5
        if self.gpio[self.vx] > self.gpio[self.vy]:
            self.gpio[0xf] = 1
        else:
            self.gpio[0xf] = 0
        self.gpio[self.vx] -= self.gpio[self.vy]
        self.gpio[self.vx] &= 0xff

    def _8ZZE(self):
        #shift vx left 1
        self.gpio[0xf] = (self.gpio[self.vx] & 0x00f0) >> 7 #if the most significant bit of vx is 1, vf is set to 1, else 0
        self.gpio[0xf] = self.gpio[self.vx] & 0x0001
        self.gpio[self.vx] <<= 0xff

    def _9ZZZ(self):
        #skip next instruction if vx != vy
        if self.gpio[self.vx] != self.gpio[self.vx]:
            self.pc += 2

    def _AZZZ(self):
        #set I to nnn
        self.index = self.opcode & 0x0fff
    
    def _BZZZ(self):
        #jump to location nnn + v0
        self.pc = (self.opcode & 0x0fff) + self.gpio[0]
    
    def _CZZZ(self):
        #set vx to random byte AND kk
        r = int(random.random() * 0xff)
        self.gpio[self.vx] = r & (self.opcode & 0x00ff)
        self.gpio[self.vx] &= 0xff
    
    def _DZZZ(self):
        #draws sprite at mem loc I
        self.gpio[0xf] = 0
        x = self.gpio[self.vx] & 0xff
        y = self.gpio[self.vy] & 0xff
        height = self.opcode & 0x000f
        row = 0
        while row < height:
            curr_row = self.memory[row + self.index]
            pixel_offset = 0
            while pixel_offset < 8:
                loc = x + pixel_offset + ((y + row) * 64)
                pixel_offset += 1
                if (y + row) >= 32 or (x + pixel_offset - 1) >= 64:
                    #ignore pixels outside of the screen
                    continue
                mask = 1 << 8-pixel_offset
                curr_pixel = (curr_row & mask) >> (8-pixel_offset)
                self.display_buffer[loc] ^= curr_pixel
                if self.display_buffer[loc] == 0:
                    self.gpio[0xf] = 1
                else:
                    self.gpio[0xf] = 0
            row += 1
        self.should_draw = True
                
    def _EZZZ(self):
        #Another conflict
        extracted_op = self.opcode & 0xf00f
        try:
            self.funcmap[extracted_op]()
        except:
            if allow_logging:
                with open("log.txt", "a") as f:
                    f.write(f"Unknown Instruction (at _EZZZ): {hex(extracted_op)}\n")
    
    def _EZZE(self):
        #skip next instruction if key stored in vx is pressed
        key = self.gpio[self.vx] & 0xf
        if self.key_inputs[key] == 1:
            self.pc += 2

    def _EZZ1(self):
        #skip next instruction if key stored in vx isn't pressed
        key = self.gpio[self.vx] & 0xf
        if self.key_inputs[key] == 0:
            self.pc += 2

    def _FZZZ(self):
        #Another conflict
        extracted_op = self.opcode & 0xf0ff
        try:
            self.funcmap[extracted_op]()
        except:
            if allow_logging:
                with open("log.txt", "a") as f:
                    f.write(f"Unknown Instruction (at _FZZZ): {hex(extracted_op)}\n")

    def _FZ07(self):
        #set vx to delay timer
        self.gpio[self.vx] = self.delay_timer 
    
    def _FZ0A(self):
        #wait for keypress
        ret = self.get_key()
        if ret >= 0:
            self.gpio[self.vx] = ret
        else:
            self.pc -= 2
    
    def _FZ15(self):
        #set delay timer to vx
        self.delay_timer = self.gpio[self.vx]
    
    def _FZ18(self):
        #set sound timer to vx
        self.sound_timer = self.gpio[self.vx]
    
    def _FZ1E(self):
        #set i to i + vx. if overflow, vf = 1
        self.index += self.gpio[self.vx]
        if self.index > 0xfff:
            self.gpio[0xf] = 1
            self.index &= 0xfff
        else:
            self.gpio[0xf] = 0

    def _FZ29(self):
        #set i to loc of sprite for digit vx
        self.index = (5*(self.gpio[self.vx])) & 0xfff

    def _FZ33(self):
        #store number as bcd in i, i+1, i+2

        self.memory[self.index] = self.gpio[self.vx] / 100
        self.memory[self.index+1] = (self.gpio[self.vx] % 100) / 10
        self.memory[self.index+2] = self.gpio[self.vx]  / 10

    def _FZ55(self):
        #store registers v0 to vx in memory starting at loc I

        i = 0
        while i <= self.vx:
            self.memory[self.index+1] = self.gpio[i]
            i += 1
        self.index += (self.vx) + 1

    def _FZ65(self):
        #read registers v0 to vx from memory starting at loc i (reverse of FZ55)
        i = 0
        while i <= self.vx:
            self.gpio[i] = self.memory[self.index+1]
            i += 1
        self.index += (self.vx) + 1

    #main

    def initialize(self):
        #fonts
        self.fonts = [0xF0, 0x90, 0x90, 0x90, 0xF0, # 0
           0x20, 0x60, 0x20, 0x20, 0x70, # 1
           0xF0, 0x10, 0xF0, 0x80, 0xF0, # 2
           0xF0, 0x10, 0xF0, 0x10, 0xF0, # 3
           0x90, 0x90, 0xF0, 0x10, 0x10, # 4
           0xF0, 0x80, 0xF0, 0x10, 0xF0, # 5
           0xF0, 0x80, 0xF0, 0x90, 0xF0, # 6
           0xF0, 0x10, 0x20, 0x40, 0x40, # 7
           0xF0, 0x90, 0xF0, 0x90, 0xF0, # 8
           0xF0, 0x90, 0xF0, 0x10, 0xF0, # 9
           0xF0, 0x90, 0xF0, 0x90, 0x90, # A
           0xE0, 0x90, 0xE0, 0x90, 0xE0, # B
           0xF0, 0x80, 0x80, 0x80, 0xF0, # C
           0xE0, 0x90, 0x90, 0x90, 0xE0, # D
           0xF0, 0x80, 0xF0, 0x80, 0xF0, # E
           0xF0, 0x80, 0xF0, 0x80, 0x80  # F
           ]

        #funcmap stores functions
        self.funcmap = {0x0000: self._0ZZZ,
                    0x00e0: self._0ZZ0,
                    0x00ee: self._0ZZE,
                    0x1000: self._1ZZZ,
                    0x2000: self._2ZZZ,
                    0x3000: self._3ZZZ,
                    0x4000: self._4ZZZ,
                    0x5000: self._5ZZZ,
                    0x6000: self._6ZZZ,
                    0x7000: self._7ZZZ,
                    0x8000: self._8ZZZ,
                    0x8FF0: self._8ZZ0,
                    0x8FF1: self._8ZZ1,
                    0x8FF2: self._8ZZ2,
                    0x8FF3: self._8ZZ3,
                    0x8FF4: self._8ZZ4,
                    0x8FF5: self._8ZZ5,
                    0x8FF6: self._8ZZ6,
                    0x8FF7: self._8ZZ7,
                    0x8FFE: self._8ZZE,
                    0x9000: self._9ZZZ,
                    0xA000: self._AZZZ,
                    0xB000: self._BZZZ,
                    0xC000: self._CZZZ,
                    0xD000: self._DZZZ,
                    0xE000: self._EZZZ,
                    0xE00E: self._EZZE,
                    0xE001: self._EZZ1,
                    0xF000: self._FZZZ,
                    0xF007: self._FZ07, 
                    0xF00A: self._FZ0A, 
                    0xF015: self._FZ15,
                    0xF018: self._FZ18, 
                    0xF01E: self._FZ1E, 
                    0xF029: self._FZ29, 
                    0xF033: self._FZ33, 
                    0xF055: self._FZ55, 
                    0xF065: self._FZ65,
                    }

        #CHIP8 has memory with 4096 bytes
        self.memory = [0]*4096

        #CHIP8 has 16 8-bit registers
        #Registers store values for operations
        self.gpio = [0]*16

        #64x32 display plus buzzer
        self.display_buffer = [0]*64*32 # 64*32

        #stack pointer, includes the address of the topmost stack item. Max items is 16
        self.stack = []

        #16-button inputs
        self.key_inputs = [0]*16  
        
        #current instruction to be preformed
        self.opcode = 0

        #index register and program counter is 16-bit
        self.index = 0
        self.pc = 0x200 #as the interpreter occupies the first slot, we need to point it to the offset

        #2 timer registers
        self.delay_timer = 0
        self.sound_timer = 0

        #only update when needed
        self.should_draw = False
        
        i = 0
        while i < 80:
        # load the font set into memory
            self.memory[i] = self.fonts[i]
            i += 1
        
        #start curses
        pyxel.init(64, 32) #64x32

    def load_rom(self, path):
        with open(path, "rb") as f: rom_binary = f.read()

        #instruction 0
        i = 0

        while i < len(rom_binary):
            #set memory to instruction
            self.memory[i+0x200] = rom_binary[i]
            i += 1
    
    def cycle(self):
        #get opcode from memory
        self.opcode = self.memory[self.pc] << 8 | self.memory[self.pc + 1]

        #extract nibbles with bitwise ops to get assoc registers. general registers used by almost all opcodes
        self.vx = (self.opcode & 0x0f00) >> 8
        self.vy = (self.opcode & 0x00f0) >> 4

        self.pc += 2

        #check the opcode, look it up in our dict, and execute it

        extracted_op = self.opcode & 0xf000 #extract the opcode (with bitwise AND)

        if allow_logging:
            with open("log.txt", "a") as f:
                f.write(f"Running instruction {hex(self.opcode)}, extracted {extracted_op}\n")

        try:
            self.funcmap[extracted_op]()
        except:
            if allow_logging:
                with open("log.txt", "a") as f:
                    f.write(f"Unknown Instruction: {hex(extracted_op)}\n")

        #decrement the timers
        if self.delay_timer > 0:
            self.delay_timer -= 1
        if self.sound_timer > 0:
            self.sound_timer -= 1
            if self.sound_timer == 0:
                pyxel.play(0, 5)

    def draw(self):
        if self.should_draw:
            i = 0
            while i < 2048:
                x = (i%64)
                y = (i//64)

                if self.display_buffer[i] == 1:
                    pyxel.pix(x, y, pixon_state)
                else:
                    pyxel.pix(x, y, pixoff_state)
                i += 1
            self.should_draw = False

    def get_key(self):
        i = 0
        while i < 16:
            if self.key_inputs[i] == 1:
                return i
            i += 1
        return -1
    
    def updatebtn(self):
        for symbol in KEY_MAP:
            if pyxel.btnp(symbol):
                self.key_inputs[KEY_MAP[symbol]] = 1
#                with open("log.txt", "a") as f:
#                    f.write(f"Button Pressed: {symbol}\n {self.key_inputs}")
            if pyxel.btnr(symbol):
                self.key_inputs[KEY_MAP[symbol]] = 0
#               with open("log.txt", "a") as f:
#                    f.write(f"Button Released: {symbol}\n {self.key_inputs}")

    def main(self):
        self.initialize()
        self.load_rom(input("Enter rom path:"))
        pyxel.run(self._update, self.draw)

    def _update(self):
        self.updatebtn()
        self.cycle()

if __name__ == "__main__":
    CPU().main()