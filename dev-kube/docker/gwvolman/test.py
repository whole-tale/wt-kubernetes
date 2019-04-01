#!/usr/bin/python3

class C1:
	def __init__(self):
		print("C1.__init__()")
		self.p = "C1P0"
	
	def m(self):
		print("C1.m(%s)" % self.p)
	
	def set(self, p):
		self.p = p

class C2:
	def __init__(self):
		print("C2.__init__()")
	
	def m(self, p):
		print("C2.m(%s)" % p)

cls = C1

def tset(self, p):
	cls.set(self, p)

def tm(self):
	cls.m(self)


inst = cls()

tm(inst)

tset(inst, "C1P1")

tm(inst)